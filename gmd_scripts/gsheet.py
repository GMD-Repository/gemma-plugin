__author__ = 'Geosptial Management Division'
__date__ = '2025-12-5'
__copyright__ = '(C) 2025, Geosptial Management Division'



def sync_mbi_layers():
    import subprocess
    import pip
    import importlib
    from . import gmdhelpers

    required_packages = ["gspread",
                         "google-auth",
                         "geopandas"]

    for i in required_packages:
        gmdhelpers.install_package(i)

    import geopandas
    import gspread
    from google.oauth2.service_account import Credentials
    import os

    GPKG_FOLDER = r"C:\PSA-GIS\2026 1Map\Preliminary Output"
    #TOTAL_GPKG_FOLDER = r"C:\PSA-GIS\2026 1Map\Total Case"

    
    # ================= AUTH =================
    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    
    gc = gspread.authorize(
        Credentials.from_service_account_file(
            os.path.join(os.path.dirname(os.path.dirname(__file__)), 'references/service_account.json'),
            scopes=SCOPES
        )
    )
    sh = gc.open("Copy of Project 1Map Monitoring")
    worksheet = sh.worksheet("Sheet7")

    print("Connected to Google Sheets successfully!")

    # ================= READ GPKG =================
    def get_gpkg_files(folder):
        return [os.path.join(folder, f) for f in os.listdir(folder) if f.endswith('.gpkg')]

    gpkg_files = get_gpkg_files(GPKG_FOLDER) + get_gpkg_files(TOTAL_GPKG_FOLDER)

    data = []
    total_cases = {}  # (province, mbi_type) -> count
    remaining_cases = {}  # (province, mbi_type) -> count
    province_date = {}  # province -> date

    for gpkg in gpkg_files:
        # Extract date from filename
        filename = os.path.basename(gpkg)
        parts = filename.split('_')
        if len(parts) >= 3:
            date_part = parts[2] + '_' + parts[3].split('.')[0]  # YYYYMMDD_HHMMSS
        else:
            date_part = ''

        layers = gpd.list_layers(gpkg)
        for layer_name in layers['name']:
            if layer_name == 'layer_styles':
                continue  # Skip styles
            gdf = gpd.read_file(gpkg, layer=layer_name)
            for _, row in gdf.iterrows():
                region = row.get('region', '')
                province = row.get('province', '')
                if gpkg in get_gpkg_files(GPKG_FOLDER):  # Preliminary
                    mbi_type = row.get('mbi_type', '')
                    if region and province and mbi_type:
                        data.append({
                            'region': region,
                            'province': province,
                            'mbi_type': mbi_type
                        })
                        province_date[province] = date_part
                        key = (province, mbi_type)
                        remaining_cases[key] = remaining_cases.get(key, 0) + 1
                if gpkg in get_gpkg_files(TOTAL_GPKG_FOLDER):  # Total
                    mbi_type = row.get('mbi_type', '')
                    if province and mbi_type:
                        key = (province, mbi_type)
                        total_cases[key] = total_cases.get(key, 0) + 1

    print(f"Collected {len(data)} entries from preliminary GPKG.")
    print(f"Total cases per province and MBI Type: {total_cases}")

    # ================= READ SHEET =================
    all_values = worksheet.get_all_values()
    expected_headers = ['Region', 'Province', 'MBI Type', 'Total Number of Cases', 'Date Updated', 'Number of Remaining Cases']
    if all_values and all_values[0] == expected_headers:
        headers = all_values[0]
    else:
        headers = expected_headers
    print(f"Headers: {headers}")
    sheet_data = [dict(zip(headers, row)) for row in all_values[1:]]
    print(f"Read {len(sheet_data)} rows from sheet.")

    # Assume sheet has columns: region, province, mbi_type, etc.
    # We need to match and update mbi_type based on region and province.

    # Create a set for unique combinations
    unique_combinations = set()
    for item in data:
        combo = (item['region'], item['province'], item['mbi_type'])
        unique_combinations.add(combo)

    print(f"Unique region-province-mbi_type combinations: {len(unique_combinations)}")

    # Since sheet has 0 rows, populate with the data
    if len(sheet_data) == 0:
        updated_values = [headers]
        sorted_unique = sorted(unique_combinations, key=lambda x: x[0])  # Sort by region
        for region, province, mbi_type in sorted_unique:
            total_num = total_cases.get((province, mbi_type), 0)
            remaining_num = remaining_cases.get((province, mbi_type), 0)
            date_up = province_date.get(province, '')
            row = [region, province, mbi_type, total_num, date_up, remaining_num]  # Fill other columns
            updated_values.append(row)
        worksheet.update(values=updated_values, range_name='A1')
        print("Populated sheet with GPKG data.")
    else:
        # Update existing - overwrite with new data
        updated_values = [headers]
        sorted_unique = sorted(unique_combinations, key=lambda x: x[0])  # Sort by region
        for region, province, mbi_type in sorted_unique:
            total_num = total_cases.get((province, mbi_type), 0)
            remaining_num = remaining_cases.get((province, mbi_type), 0)
            date_up = province_date.get(province, '')
            row = [region, province, mbi_type, total_num, date_up, remaining_num]  # Fill other columns
            updated_values.append(row)
        worksheet.update(values=updated_values, range_name='A1')
        print("Updated sheet with new GPKG data.")


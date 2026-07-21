# Sync MBI Layer

The **Sync MBI Layer** tool synchronizes your MBI (Map-Based Inventory) reporting layers with **Google Sheets** for centralized tracking and monitoring of boundary resolution progress.

## Access

- **Menu:** GeMa → Reports → Sync MBI Layer

## When to Use

Use this tool when:

- You need to update the centralized tracking sheet with your latest MBI results
- Supervisors need a real-time overview of boundary resolution progress across PSOs
- You want to share MBI status data with the team without sending files manually

## How It Works

1. The tool reads the current MBI layer data from your QGIS project
2. It connects to a configured Google Sheet using the Google Sheets API
3. Layer data is synchronized to the spreadsheet for centralized tracking

## Requirements

- An active internet connection
- Properly configured Google Sheets API credentials
- The MBI layers must be loaded in your QGIS project

::: tip
Run the Sync MBI Layer tool after completing a round of boundary checks to keep the centralized tracking sheet up to date. This helps supervisors monitor progress across all PSOs in real time.
:::

import { defineConfig } from 'vitepress'

// https://vitepress.dev/reference/site-config
export default defineConfig({
  base: '/gemma-plugin/',
  srcDir: "user-guide",

  title: "GEMMA Plugin",
  description: "GIS Extension for Map Management and Analysis — A QGIS processing plugin by the Geospatial Management Division (GMD) of the Philippine Statistics Authority.",

  head: [
    ['meta', { name: 'author', content: 'Geospatial Management Division — Philippine Statistics Authority' }],
    ['meta', { name: 'keywords', content: 'QGIS, GIS, plugin, GEMMA, GMD, PSA, 1Map, QField, geometry, overlaps, gaps' }],
  ],

  themeConfig: {
    // https://vitepress.dev/reference/default-theme-config
    logo: '/icon.png',
    siteTitle: 'GEMMA Plugin',

    nav: [
      { text: 'Home', link: '/' },
      { text: 'Getting Started', link: '/getting-started' },
      {
        text: 'Tools',
        items: [
          { text: 'MBI Checker', link: '/tools/mbi-checker' },
          { text: 'Fill Polygon Gaps', link: '/tools/fill-polygon-gaps' },
          { text: 'Export Preliminary Polygons', link: '/tools/export-preliminary-polygons' },
          { text: 'Update LGU PSGC Metadata', link: '/tools/update-metadata' },
          { text: 'Fix LGU CRS / Geometry', link: '/tools/fix-lgu-crs' },
          { text: 'Geometry Repair Toolkit', link: '/tools/geometry-repair-toolkit' },
          { text: 'Package for QField', link: '/tools/package-qfield' },
          { text: 'Create Enumeration Areas', link: '/tools/create-enumeration-areas' },
        ]
      },
      { text: 'Changelog', link: '/changelog' },
      {
        text: 'Download',
        link: 'https://github.com/GMD-Repository/gemma-plugin/releases/latest'
      },
    ],

    sidebar: [
      {
        text: 'Introduction',
        items: [
          { text: 'Getting Started', link: '/getting-started' },
          { text: 'Changelog', link: '/changelog' },
        ]
      },
      {
        text: '1Map Tools',
        collapsed: false,
        items: [
          { text: 'MBI Checker', link: '/tools/mbi-checker' },
          { text: 'Fill Polygon Gaps', link: '/tools/fill-polygon-gaps' },
          { text: 'Export Preliminary Polygons', link: '/tools/export-preliminary-polygons' },
          { text: 'Update LGU PSGC Metadata', link: '/tools/update-metadata' },
          { text: 'Fix LGU CRS / Geometry', link: '/tools/fix-lgu-crs' },
        ]
      },
      {
        text: 'Geometry & Repair',
        collapsed: false,
        items: [
          { text: 'Geometry Repair Toolkit', link: '/tools/geometry-repair-toolkit' },
        ]
      },
      {
        text: 'QField & Enumeration',
        collapsed: false,
        items: [
          { text: 'Package for QField', link: '/tools/package-qfield' },
          { text: 'Create Enumeration Areas', link: '/tools/create-enumeration-areas' },
        ]
      },
    ],

    socialLinks: [
      { icon: 'github', link: 'https://github.com/GMD-Repository/gemma-plugin' }
    ],

    footer: {
      message: 'Developed by the Geospatial Management Division',
      copyright: '© 2025–2026 Philippine Statistics Authority'
    },

    search: {
      provider: 'local'
    },

    editLink: {
      pattern: 'https://github.com/GMD-Repository/gemma-plugin/edit/main/docs/user-guide/:path',
      text: 'Edit this page on GitHub'
    },
  }
})

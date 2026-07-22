import DefaultTheme from 'vitepress/theme'
import type { Theme } from 'vitepress'
import Layout from './Layout.vue'
import './custom.css'

import QGISRepositoryCard from './components/QGISRepositoryCard.vue'
import LatestReleaseCard from './components/LatestReleaseCard.vue'
import Contributors from './components/Contributors.vue'

const theme: Theme = {
  extends: DefaultTheme,
  Layout,
  enhanceApp({ app }) {
    app.component('QGISRepositoryCard', QGISRepositoryCard)
    app.component('LatestReleaseCard', LatestReleaseCard)
    app.component('Contributors', Contributors)
  }
}

export default theme

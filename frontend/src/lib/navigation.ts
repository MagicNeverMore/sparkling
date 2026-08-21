export interface NavChildItem {
  to: string
  labelKey: string
}

export interface NavItem {
  to?: string
  labelKey: string
  icon: string
  children?: readonly NavChildItem[]
}

export const navItems: readonly NavItem[] = [
  { to: '/inbox', labelKey: 'nav.inbox', icon: 'Inbox' },
  { to: '/graph', labelKey: 'nav.graph', icon: 'Network' },
  { to: '/search', labelKey: 'nav.search', icon: 'Search' },
  { to: '/trends', labelKey: 'nav.trends', icon: 'TrendingUp' },
  {
    labelKey: 'nav.socialMedia',
    icon: 'BarChart3',
    children: [
      { to: '/social-media/list', labelKey: 'nav.socialMediaList' },
      { to: '/social-media/topics', labelKey: 'nav.socialMediaTopics' },
    ],
  },
  { to: '/tasks', labelKey: 'nav.tasks', icon: 'CheckSquare' },
  { to: '/user', labelKey: 'nav.user', icon: 'User' },
  { to: '/settings', labelKey: 'nav.settings', icon: 'Settings' },
]

export const mobileTabItems = navItems.filter((item) => item.to && !item.children)

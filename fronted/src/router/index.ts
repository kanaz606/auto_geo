/**
 * 路由配置
 * 我用这个来管理应用路由！
 */

import { createRouter, createWebHashHistory, type RouteRecordRaw } from 'vue-router'

// 路由定义
const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: () => import('@/views/layout/MainLayout.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/dashboard/DashboardPage.vue'),
        meta: { title: '首页', icon: 'House' }, // 原来的概览改为首页，避免名字冲突
      },
      {
        path: 'data-report',
        name: 'DataReport',
        component: () => import('@/views/report/DataReport.vue'),
        meta: { title: '数据报表', icon: 'DataAnalysis' },
      },
      {
        path: 'accounts',
        name: 'Accounts',
        component: () => import('@/views/account/AccountList.vue'),
        meta: { title: '账号管理', icon: 'User' },
      },
      {
        path: 'accounts/add',
        name: 'AccountAdd',
        component: () => import('@/views/account/AccountAdd.vue'),
        meta: { title: '添加账号', hidden: true },
      },
      {
        path: 'articles',
        name: 'Articles',
        component: () => import('@/views/article/ArticleList.vue'),
        meta: { title: '文章管理', icon: 'Document' },
      },
      {
        path: 'articles/add',
        name: 'ArticleAdd',
        component: () => import('@/views/article/ArticleEdit.vue'),
        meta: { title: '新建文章', hidden: true },
      },
      {
        path: 'articles/edit/:id',
        name: 'ArticleEdit',
        component: () => import('@/views/article/ArticleEdit.vue'),
        meta: { title: '编辑文章', hidden: true },
      },
      {
        path: 'publish',
        name: 'Publish',
        component: () => import('@/views/publish/PublishPage.vue'),
        meta: { title: '批量发布', icon: 'Promotion' },
      },
      {
        path: 'history',
        name: 'History',
        component: () => import('@/views/publish/PublishHistory.vue'),
        meta: { title: '发布记录', icon: 'Clock' },
      },
      {
        path: 'settings',
        name: 'Settings',
        component: () => import('@/views/settings/SettingsPage.vue'),
        meta: { title: '设置', icon: 'Setting' },
      },
      // ==================== GEO系统路由 ====================
      // 🌟 新增：数据概览（仪表盘）放在GEO的第一位
      {
        path: 'geo/dashboard',
        name: 'GeoDashboard',
        component: () => import('@/views/geo/Dashboard.vue'),
        meta: { title: '数据概览', icon: 'PieChart' }, 
      },
      {
        path: 'geo/projects',
        name: 'GeoProjects',
        component: () => import('@/views/geo/Projects.vue'),
        meta: { title: 'GEO项目管理', icon: 'Grid' },
      },
      {
        path: 'geo/keywords',
        name: 'GeoKeywords',
        component: () => import('@/views/geo/Keywords.vue'),
        meta: { title: '关键词蒸馏', icon: 'MagicStick' },
      },
      {
        path: 'geo/articles',
        name: 'GeoArticles',
        component: () => import('@/views/geo/Articles.vue'),
        meta: { title: '文章生成', icon: 'EditPen' },
      },
      {
        path: 'geo/monitor',
        name: 'GeoMonitor',
        component: () => import('@/views/geo/Monitor.vue'),
        meta: { title: '收录监控', icon: 'Monitor' },
      },
            {
        path: 'candidates',
        name: 'Candidates',
        component: () => import('@/views/candidate/CandidatePage.vue'),
        meta: { title: '候选人管理', icon: 'UserFilled' },
      },

      // ==================== 知识库管理路由 ====================
      {
        path: 'knowledge',
        name: 'Knowledge',
        component: () => import('@/views/knowledge/KnowledgePage.vue'),
        meta: { title: '知识库管理', icon: 'Reading' },
      },
      // ==================== 定时任务管理路由 ====================
      {
        path: 'scheduler',
        name: 'Scheduler',
        component: () => import('@/views/scheduler/SchedulerPage.vue'),
        meta: { title: '定时任务', icon: 'Timer' },
      },
    ],
  },
]

// 创建路由实例
const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

// 路由守卫
router.beforeEach((to, _from, next) => {
  // 设置页面标题
  if (to.meta?.title) {
    document.title = `${to.meta.title} - AutoGeo`
  }
  next()
})

export default router
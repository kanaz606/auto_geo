<template>
  <div class="articles-page">
    <!-- 选择区域 -->
    <div class="section">
      <h2 class="section-title">生成文章</h2>
      <el-form :inline="true" :model="generateForm" class="generate-form">
        <el-form-item label="选择项目">
          <el-select
            v-model="generateForm.projectId"
            placeholder="请选择项目"
            style="width: 180px"
            @change="onProjectChange"
          >
            <el-option
              v-for="project in projects"
              :key="project.id"
              :label="project.name"
              :value="project.id"
            />
          </el-select>
        </el-form-item>
        
        <el-form-item label="选择关键词">
          <el-select
            v-model="generateForm.keywordId"
            placeholder="请选择关键词"
            style="width: 180px"
            :disabled="!generateForm.projectId"
          >
            <!-- 🌟 兼容处理字段名 -->
            <el-option
              v-for="keyword in keywords"
              :key="keyword.id"
              :label="keyword.keyword || keyword.name"
              :value="keyword.id"
            />
          </el-select>
        </el-form-item>
        
        <el-form-item label="发布平台">
          <el-select v-model="generateForm.platform" style="width: 120px">
            <el-option label="知乎" value="zhihu" />
            <el-option label="百家号" value="baijiahao" />
            <el-option label="搜狐号" value="sohu" />
            <el-option label="头条号" value="toutiao" />
          </el-select>
        </el-form-item>

        <el-form-item label="定时发布">
          <el-date-picker
            v-model="generateForm.publishTime"
            type="datetime"
            placeholder="立即发布 (留空)"
            value-format="YYYY-MM-DD HH:mm:ss"
            style="width: 200px"
            clearable
          />
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            :loading="generating"
            :disabled="!generateForm.keywordId"
            @click="generateArticle"
          >
            <el-icon><MagicStick /></el-icon>
            生成文章
          </el-button>
        </el-form-item>
      </el-form>
    </div>

    <!-- 文章列表 -->
    <div class="section mt-20">
      <div class="section-header">
        <h2 class="section-title">文章列表</h2>
        <el-button @click="loadArticles" size="small" type="primary" plain>
          <el-icon><Refresh /></el-icon>
          刷新列表
        </el-button>
      </div>

      <el-table
        v-loading="articlesLoading"
        :data="articles"
        stripe
        style="width: 100%"
        height="500"
      >
        <el-table-column prop="title" label="标题" min-width="180">
          <template #default="{ row }">
            {{ row.title || '（内容生成中...）' }}
          </template>
        </el-table-column>
        <el-table-column prop="platform" label="平台" width="90">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ getPlatformName(row.platform) }}</el-tag>
          </template>
        </el-table-column>
        
        <el-table-column label="发布状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getPublishStatusType(row.publish_status)" size="small">
              {{ getPublishStatusText(row.publish_status) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="收录状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getIndexStatusType(row.index_status)" size="small" effect="dark">
              {{ getIndexStatusText(row.index_status) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="评分" width="70">
          <template #default="{ row }">
            <span v-if="row.quality_score" :class="getScoreClass(row.quality_score)">
              {{ row.quality_score }}
            </span>
            <span v-else>-</span>
          </template>
        </el-table-column>

        <el-table-column label="创建时间" width="160">
          <template #default="{ row }">
            <span class="text-muted">{{ formatDate(row.created_at) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" size="small" link @click="previewArticle(row)">预览</el-button>
            <el-button
              type="success"
              size="small"
              link
              :disabled="row.publish_status === 'generating'"
              @click="handleCheckQuality(row)"
            >质检</el-button>
            <el-button type="danger" size="small" link @click="deleteArticle(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 文章预览对话框 -->
    <el-dialog 
      v-model="showPreviewDialog" 
      :title="currentArticle?.title || '文章预览'" 
      width="800px"
      destroy-on-close
    >
      <div v-if="currentArticle" class="article-preview-scroll">
        <div class="markdown-body" v-html="renderMarkdown(currentArticle.content)"></div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, Refresh } from '@element-plus/icons-vue'
import { geoKeywordApi, geoArticleApi, indexCheckApi } from '@/services/api'
import MarkdownIt from 'markdown-it'

const md = new MarkdownIt({ html: true, linkify: true })
const renderMarkdown = (content: string) => content ? md.render(content) : '暂无内容'

// 状态
const projects = ref<any[]>([])
const keywords = ref<any[]>([])
const articles = ref<any[]>([])
const articlesLoading = ref(false)
const generating = ref(false)
const showPreviewDialog = ref(false)
const currentArticle = ref<any>(null)

const generateForm = ref({
  projectId: null as number | null,
  keywordId: null as number | null,
  platform: 'zhihu',
  publishTime: '' 
})

// 数据加载
const loadProjects = async () => {
  try {
    const res: any = await geoKeywordApi.getProjects()
    projects.value = Array.isArray(res) ? res : (res?.data || [])
  } catch (error) { console.error(error) }
}

const onProjectChange = async () => {
  generateForm.value.keywordId = null
  keywords.value = []
  if (generateForm.value.projectId) {
    try {
      const res: any = await geoKeywordApi.getProjectKeywords(generateForm.value.projectId)
      keywords.value = Array.isArray(res) ? res : (res?.data || [])
    } catch (error) { console.error(error) }
  }
}

// 🌟 核心修复：调用 getArticles 且增加数据解析防御
const loadArticles = async () => {
  articlesLoading.value = true
  try {
    console.log("正在请求文章列表...")
    const res: any = await geoArticleApi.getArticles()
    console.log("文章列表接口原始返回:", res)
    
    if (Array.isArray(res)) {
      articles.value = res
    } else if (res && Array.isArray(res.data)) {
      articles.value = res.data
    } else {
      articles.value = []
    }
  } catch (error) {
    console.error('加载文章失败:', error)
  } finally {
    articlesLoading.value = false
  }
}

// 操作
const generateArticle = async () => {
  if (!generateForm.value.keywordId) return
  const project = projects.value.find(p => p.id === generateForm.value.projectId)
  
  generating.value = true
  try {
    const res = await geoArticleApi.generate({
      keyword_id: generateForm.value.keywordId as number,
      company_name: project?.company_name || '默认公司',
      platform: generateForm.value.platform
    })
    if (res.success) {
      ElMessage.success('任务提交成功')
      await loadArticles()
    }
  } finally { generating.value = false }
}

const handleCheckQuality = async (row: any) => {
    try {
        const res = await geoArticleApi.checkQuality(row.id)
        if (res.success) {
            ElMessage.success('质检评分已更新')
            await loadArticles()
        }
    } catch (e) { console.error(e) }
}

const deleteArticle = async (article: any) => {
  try {
    await ElMessageBox.confirm('确定要删除吗？', '警告', { type: 'warning' })
    await geoArticleApi.delete(article.id)
    ElMessage.success('已删除')
    await loadArticles()
  } catch (error) { }
}

const previewArticle = (article: any) => {
  currentArticle.value = article
  showPreviewDialog.value = true
}

// 渲染工具
const getPublishStatusType = (s: string) => ({ draft:'info', scheduled:'warning', publishing:'primary', published:'success', failed:'danger' }[s] || 'info')
const getPublishStatusText = (s: string) => ({ draft:'草稿', scheduled:'待发布', publishing:'发布中', published:'已发布', failed:'失败' }[s] || s)
const getIndexStatusType = (s: string) => ({ uncheck:'info', indexed:'success', not_indexed:'danger' }[s] || 'info')
const getIndexStatusText = (s: string) => ({ uncheck:'未检测', indexed:'已收录', not_indexed:'未收录' }[s] || '未检测')
const getPlatformName = (p: string) => ({ zhihu:'知乎', baijiahao:'百家号', sohu:'搜狐', toutiao:'头条' }[p] || p)
const getScoreClass = (s: number) => s >= 80 ? 'text-success' : (s >= 60 ? 'text-warning' : 'text-danger')
const formatDate = (d?: string) => d ? new Date(d).toLocaleString() : '-'

onMounted(() => {
  loadProjects()
  loadArticles()
})
</script>

<style scoped lang="scss">
.articles-page { padding: 20px; }
.section { background: #1e1e1e; border-radius: 12px; padding: 24px; margin-bottom: 24px; border: 1px solid rgba(255,255,255,0.05); }
.section-title { color: #fff; margin-bottom: 20px; font-size: 18px; font-weight: 600; }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.text-muted { color: #888; font-size: 13px; }
.text-success { color: #67c23a; }
.text-warning { color: #e6a23c; }
.text-danger { color: #f56c6c; }
.article-preview-scroll { max-height: 70vh; overflow-y: auto; padding: 20px; background: #fff; color: #333; border-radius: 8px; }
.markdown-body { line-height: 1.8; :deep(img) { max-width: 100%; border-radius: 8px; margin: 10px 0; } }
</style>
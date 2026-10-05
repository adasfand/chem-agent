<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ArrowUpRight, Settings2, RotateCcw, X, BookOpen, Wrench, Plus } from '@lucide/vue'
import { createWorkbench } from './composables/useWorkbench'
import WorkbenchSidebar from './components/WorkbenchSidebar.vue'
import TaskComposer from './components/TaskComposer.vue'
import ResultPanel from './components/ResultPanel.vue'
import KnowledgeLibrary from './components/KnowledgeLibrary.vue'
const workbench = createWorkbench()
const { state, busy, running, canSubmit } = workbench
const view = ref<'workbench' | 'knowledge'>('workbench')
const knowledgeId = ref<string | null>(null)
const settingsDialog = ref<HTMLDialogElement>()
const connection = computed(() =>
  state.booting
    ? '连接中'
    : !state.connected
      ? '后端未连接'
      : state.bootstrap?.configured
        ? 'API 已配置'
        : 'API 待配置',
)
function newTask(question = '') {
  workbench.startNew(question)
  view.value = 'workbench'
}
function selectJob(id: string) {
  view.value = 'workbench'
  void workbench.loadJob(id)
}
function openKnowledge(id: string) {
  knowledgeId.value = id
  view.value = 'knowledge'
}
onMounted(() => {
  void workbench.boot()
})
onUnmounted(workbench.dispose)
</script>
<template>
  <div class="app-shell">
    <WorkbenchSidebar
      :view="view"
      :runs="state.runs"
      :selected="state.job?.job_id"
      :busy="busy"
      :loading-id="state.loadingId"
      @navigate="view = $event"
      @new="newTask()"
      @select="selectJob"
    />
    <main class="workspace">
      <header class="topbar">
        <div class="breadcrumbs">
          Chem Agent
          <span>/</span>
          <strong>{{ view === 'workbench' ? '任务工作台' : '知识资料库' }}</strong>
        </div>
        <div class="topbar-actions">
          <button
            class="icon-button mobile-new"
            aria-label="新建任务"
            title="新建任务"
            :disabled="busy"
            @click="newTask()"
          >
            <Plus :size="18" />
          </button>
          <span
            class="connection-indicator"
            :class="{ warning: !state.bootstrap?.configured || !state.connected }"
          >
            <i />
            {{ connection }}
          </span>
          <button
            class="icon-button"
            title="重新连接"
            aria-label="重新连接"
            :disabled="state.booting || state.submitting"
            @click="workbench.boot()"
          >
            <RotateCcw :size="17" :class="{ spinning: state.booting }" />
          </button>
          <button
            class="icon-button"
            title="运行配置"
            aria-label="运行配置"
            @click="settingsDialog?.showModal()"
          >
            <Settings2 :size="18" />
          </button>
        </div>
      </header>
      <div class="workspace-content">
        <div class="page-heading">
          <div>
            <h1>
              {{ view === 'workbench' ? '化工计算工作台' : '知识资料库' }}
            </h1>
            <p>
              {{
                view === 'workbench'
                  ? '输入工况与已知条件，查看计算过程和引用依据。'
                  : '查阅公式、变量和适用条件，核对计算所依据的资料。'
              }}
            </p>
          </div>
          <button v-if="view === 'workbench'" class="heading-link" @click="view = 'knowledge'">
            浏览知识库
            <ArrowUpRight :size="17" />
          </button>
          <button v-else class="heading-link" @click="view = 'workbench'">
            返回工作台
            <ArrowUpRight :size="17" />
          </button>
        </div>
        <label v-if="state.runs.length" class="mobile-history">
          最近任务
          <select
            :value="state.job?.job_id || ''"
            :disabled="busy || !!state.loadingId"
            @change="selectJob(($event.target as HTMLSelectElement).value)"
          >
            <option value="" disabled>选择本次会话的记录</option>
            <option v-for="run in state.runs" :key="run.job_id" :value="run.job_id">
              {{ run.question }}
            </option>
          </select>
        </label>
        <div v-if="state.notice" class="notice" :class="state.notice.kind" role="status">
          <span>{{ state.notice.message }}</span>
          <button class="icon-button" aria-label="关闭提示" @click="state.notice = null">
            <X :size="15" />
          </button>
        </div>
        <template v-if="view === 'workbench'">
          <div class="workspace-summary">
            <div>
              <BookOpen :size="19" />
              <span>
                <strong>{{ state.bootstrap?.knowledge.length ?? '—' }}</strong>
                张本地知识卡
              </span>
            </div>
            <div>
              <Wrench :size="19" />
              <span>
                <strong>4</strong>
                个领域工具
              </span>
            </div>
            <span class="summary-label">单位换算 / 单相显热 / 混合衡算</span>
          </div>
          <div class="workbench-grid">
            <TaskComposer
              v-model:draft="state.draft"
              :busy="busy"
              :running="running"
              :configured="state.bootstrap?.configured ?? false"
              :connected="state.connected"
              :can-submit="canSubmit"
              :cancelling="state.cancelling"
              :job="state.job"
              :examples="state.bootstrap?.examples ?? []"
              @submit="workbench.submit()"
              @cancel="workbench.cancel()"
              @example="newTask"
            />
            <ResultPanel :job="state.job" :loading="!!state.loadingId" @knowledge="openKnowledge" />
          </div>
        </template>
        <KnowledgeLibrary
          v-else
          :items="state.bootstrap?.knowledge ?? []"
          :initial-id="knowledgeId"
        />
        <footer class="workspace-footer">
          <span>教学与算法演示，结果需结合实际工况复核。</span>
          <span>知识资料与运行记录保存在本机</span>
        </footer>
      </div>
    </main>
    <dialog
      ref="settingsDialog"
      class="settings-dialog"
      aria-labelledby="settings-title"
      @click="$event.target === settingsDialog && settingsDialog.close()"
    >
      <div class="dialog-heading">
        <h2 id="settings-title">运行配置</h2>
        <button class="icon-button" aria-label="关闭配置" @click="settingsDialog?.close()">
          <X :size="20" />
        </button>
      </div>
      <dl>
        <dt>后端状态</dt>
        <dd>{{ state.connected ? '已连接本机服务' : '未连接' }}</dd>
        <dt>模型</dt>
        <dd>{{ state.bootstrap?.model ?? '等待后端连接' }}</dd>
        <dt>API 密钥</dt>
        <dd>{{ state.bootstrap?.configured ? '已填写，尚不代表认证或余额有效' : '尚未配置' }}</dd>
        <dt>知识资料</dt>
        <dd>{{ state.bootstrap?.knowledge.length ?? 0 }} 张本地知识卡</dd>
      </dl>
      <p>
        在项目根目录的
        <code>.env</code>
        中填写
        <code>DEEPSEEK_API_KEY</code>
        ，重启 Python 后端，再点击“重新连接”。密钥只保存在后端。
      </p>
      <p>
        页面资源和知识卡保存在本机；模型规划和生成仍需联网。重启后端后，当前会话历史会重置，已保存的运行文件仍保留。
      </p>
      <button class="button primary" @click="settingsDialog?.close()">知道了</button>
    </dialog>
  </div>
</template>

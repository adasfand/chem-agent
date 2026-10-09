<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
  Settings2,
  RotateCcw,
  X,
  Plus,
  PanelRightClose,
  PanelRightOpen,
  BookOpen,
} from '@lucide/vue'
import { createWorkbench } from './composables/useWorkbench'
import WorkbenchSidebar from './components/WorkbenchSidebar.vue'
import TaskComposer from './components/TaskComposer.vue'
import ResultPanel from './components/ResultPanel.vue'
import KnowledgeLibrary from './components/KnowledgeLibrary.vue'
import TraceInspector from './components/TraceInspector.vue'
const workbench = createWorkbench()
const { state, busy, running, canSubmit } = workbench
const view = ref<'workbench' | 'knowledge'>('workbench')
const knowledgeId = ref<string | null>(null)
const inspectorOpen = ref(true)
const settingsDialog = ref<HTMLDialogElement>()
const connection = computed(() =>
  state.booting
    ? '连接中'
    : !state.connected
      ? '后端未连接'
      : state.bootstrap?.configured
        ? '密钥已填写'
        : '模型待配置',
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
      :connected="state.connected"
      :version="state.bootstrap?.version"
      @navigate="view = $event"
      @new="newTask()"
      @select="selectJob"
      @settings="settingsDialog?.showModal()"
    />
    <main class="workspace">
      <header class="topbar">
        <div class="breadcrumbs">
          工作空间
          <span>/</span>
          <strong>{{ view === 'workbench' ? '问答工作台' : '知识资料库' }}</strong>
        </div>
        <div class="topbar-actions">
          <button
            class="icon-button mobile-new"
            aria-label="新建问答"
            title="新建问答"
            :disabled="busy"
            @click="newTask()"
          >
            <Plus :size="18" />
          </button>
          <span
            class="connection-indicator"
            title="此状态仅说明后端连接与密钥填写情况；API 是否可用以实际任务结果为准。"
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
            <RotateCcw :size="16" :class="{ spinning: state.booting }" />
          </button>
          <button
            class="icon-button"
            title="运行配置"
            aria-label="运行配置"
            @click="settingsDialog?.showModal()"
          >
            <Settings2 :size="17" />
          </button>
          <button
            v-if="view === 'workbench'"
            class="icon-button"
            :title="inspectorOpen ? '收起依据与过程' : '展开依据与过程'"
            aria-label="切换依据与过程"
            :aria-expanded="inspectorOpen"
            aria-controls="trace-inspector"
            @click="inspectorOpen = !inspectorOpen"
          >
            <PanelRightClose v-if="inspectorOpen" :size="18" />
            <PanelRightOpen v-else :size="18" />
          </button>
        </div>
      </header>
      <div v-if="state.notice" class="notice" :class="state.notice.kind" role="status">
        <span>{{ state.notice.message }}</span>
        <button class="icon-button" aria-label="关闭提示" @click="state.notice = null">
          <X :size="15" />
        </button>
      </div>
      <label v-if="state.runs.length" class="mobile-history">
        最近问答
        <select
          :value="state.job?.job_id || ''"
          :disabled="busy || !!state.loadingId"
          @change="selectJob(($event.target as HTMLSelectElement).value)"
        >
          <option value="" disabled>选择本次会话记录</option>
          <option v-for="run in state.runs" :key="run.job_id" :value="run.job_id">
            {{ run.question }}
          </option>
        </select>
      </label>
      <div
        v-if="view === 'workbench'"
        class="workbench-layout"
        :class="{ 'inspector-hidden': !inspectorOpen }"
      >
        <section class="conversation-column" aria-label="化工问答">
          <div class="conversation-heading">
            <div>
              <h2>{{ state.job ? '任务详情' : '化工知识与计算' }}</h2>
              <p>
                {{
                  state.job
                    ? '核对结论，或补充条件继续计算'
                    : '知识问答 / 单位换算 / 显热负荷 / 混合衡算'
                }}
              </p>
            </div>
            <button class="heading-link" @click="view = 'knowledge'">
              <BookOpen :size="15" />
              知识库
            </button>
          </div>
          <ResultPanel
            :job="state.job"
            :loading="!!state.loadingId"
            :examples="state.bootstrap?.examples ?? []"
            :busy="busy"
            @example="newTask"
            @knowledge="view = 'knowledge'"
          />
          <TaskComposer
            v-model:draft="state.draft"
            :busy="busy"
            :running="running"
            :configured="state.bootstrap?.configured ?? false"
            :connected="state.connected"
            :can-submit="canSubmit"
            :cancelling="state.cancelling"
            :job="state.job"
            @submit="workbench.submit()"
            @cancel="workbench.cancel()"
          />
        </section>
        <TraceInspector
          v-if="inspectorOpen"
          id="trace-inspector"
          :job="state.job"
          :index-status="state.bootstrap?.index_status"
          :knowledge-count="state.bootstrap?.knowledge.length ?? 0"
          @knowledge="openKnowledge"
        />
      </div>
      <div v-else class="library-workspace">
        <div class="library-heading">
          <div>
            <h1>知识资料库</h1>
            <p>查阅公式、变量及适用条件，核对计算依据。</p>
          </div>
          <button class="button secondary" @click="view = 'workbench'">返回问答</button>
        </div>
        <KnowledgeLibrary :items="state.bootstrap?.knowledge ?? []" :initial-id="knowledgeId" />
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
          <X :size="19" />
        </button>
      </div>
      <dl>
        <dt>后端服务</dt>
        <dd>{{ state.connected ? '已连接本机服务' : '未连接' }}</dd>
        <dt>模型</dt>
        <dd>{{ state.bootstrap?.model ?? '等待连接' }}</dd>
        <dt>API 密钥</dt>
        <dd>{{ state.bootstrap?.configured ? '已填写，不代表认证或余额有效' : '尚未配置' }}</dd>
        <dt>知识资料</dt>
        <dd>{{ state.bootstrap?.knowledge.length ?? 0 }} 张本地知识卡</dd>
        <dt>检索状态</dt>
        <dd>{{ state.bootstrap?.index_status?.message || '等待连接' }}</dd>
      </dl>
      <p>
        模型密钥在项目根目录的
        <code>.env</code>
        中配置，修改后重启 Python 后端，再点击“重新连接”。密钥仅保存在后端。
      </p>
      <p>
        页面资源与知识卡保存在本机。模型规划、回答及 LightRAG
        关键词抽取需要联网；未建索引时使用词法检索。重启后端会重置会话历史，已保存的运行文件仍保留。
      </p>
      <button class="button primary" @click="settingsDialog?.close()">完成</button>
    </dialog>
  </div>
</template>

<script setup lang="ts">
import pkg from '../../package.json'

const version = pkg.version
const repo = 'https://github.com/MarchBeta2087/mengxi-llm-chat'

const stack = [
  { name: 'FastAPI', license: 'MIT' },
  { name: 'Starlette / Uvicorn', license: 'BSD-3-Clause' },
  { name: 'SQLAlchemy', license: 'MIT' },
  { name: 'Pydantic', license: 'MIT' },
  { name: 'cryptography', license: 'Apache-2.0 / BSD-3-Clause' },
  { name: 'argon2-cffi', license: 'MIT' },
  { name: 'httpx', license: 'BSD-3-Clause' },
  { name: 'redis-py', license: 'MIT' },
  { name: 'Alembic', license: 'MIT' },
  { name: 'Vue 3', license: 'MIT' },
  { name: 'Vite', license: 'MIT' },
  { name: 'Pinia', license: 'MIT' },
  { name: 'Vue Router', license: 'MIT' },
]

const license = `BSD 3-Clause License

Copyright (c) 2026, MarchBeta2087

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.
3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from
   this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.`
</script>

<template>
  <div class="page">
    <h2>关于</h2>

    <div class="card">
      <h1>梦溪畅谈</h1>
      <p class="sub">mengxi-llm-chat · v{{ version }}</p>
      <p class="desc">
        一个可自部署的 LLM 聊天 Web 应用：多模型、多 API Key 公私双轨管理与调度、六维限流、
        插件系统、对话加密与盲索引搜索、审计日志、可定制界面。
      </p>
      <p class="muted">
        名称取自沈括《梦溪笔谈》——"笔谈"之记录与"畅谈"之对谈双关，恰合"加密聊天记录 + AI 对谈"。
      </p>
    </div>

    <div class="card">
      <h3>许可证</h3>
      <p class="muted">本项目以 <b>BSD 3-Clause License</b> 发布。完整文本如下：</p>
      <pre class="license">{{ license }}</pre>
    </div>

    <div class="card">
      <h3>第三方组件与许可</h3>
      <table>
        <caption class="visually-hidden">第三方组件与许可证</caption>
        <thead>
          <tr>
            <th scope="col">组件</th>
            <th scope="col">许可</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in stack" :key="item.name">
            <td>{{ item.name }}</td>
            <td>{{ item.license }}</td>
          </tr>
        </tbody>
      </table>
      <p class="muted">
        上述组件均为与 BSD-3-Clause 兼容的宽松许可（MIT / BSD / Apache-2.0）。
      </p>
    </div>

    <div class="card">
      <h3>链接</h3>
      <ul>
        <li><a :href="repo" target="_blank" rel="noreferrer">源码仓库</a></li>
        <li><a :href="`${repo}/blob/main/LICENSE`" target="_blank" rel="noreferrer">LICENSE</a></li>
        <li>
          <a :href="`${repo}/blob/main/CONTRIBUTING.md`" target="_blank" rel="noreferrer">
            贡献指南
          </a>
        </li>
        <li>
          <a :href="`${repo}/blob/main/CODE_OF_CONDUCT.md`" target="_blank" rel="noreferrer">
            行为准则
          </a>
        </li>
        <li>
          <a :href="`${repo}/blob/main/SECURITY.md`" target="_blank" rel="noreferrer">
            安全政策（漏洞报告）
          </a>
        </li>
        <li>
          <a :href="`${repo}/blob/main/ACCESSIBILITY.md`" target="_blank" rel="noreferrer">
            无障碍声明
          </a>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.page {
  padding: 24px 5vw;
  height: 100vh;
  overflow-y: auto;
}
h2 {
  font-family: 'Songti SC', serif;
  color: var(--xi-dark);
}
h1 {
  font-family: 'Songti SC', serif;
  color: var(--xi-dark);
  letter-spacing: 2px;
}
h3 {
  font-size: 15px;
  color: var(--xi-dark);
  margin-bottom: 10px;
}
.card {
  margin-bottom: 18px;
}
.sub {
  font-size: 12px;
  color: var(--muted);
  margin: 4px 0 12px;
}
.desc {
  font-size: 14px;
  line-height: 1.8;
  margin-bottom: 8px;
}
.muted {
  font-size: 12px;
  color: var(--muted);
  line-height: 1.7;
}
.license {
  font-family: ui-monospace, monospace;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 12px;
  max-height: 320px;
  overflow-y: auto;
}
ul {
  padding-left: 18px;
  font-size: 13px;
  line-height: 2;
}
</style>

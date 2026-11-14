import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'
import 'highlight.js/styles/github-dark.css'
import * as api from '../api'
import { fmtTime } from '../format'
import { navigate } from '../router'
import type { KbCreateInput, KbDetail, KbDocument, KbDocumentPage, KbSummary } from '../types'

const PAGE_LIMIT = 6000

const EMPTY_FORM: KbCreateInput = {
  name: '',
  description: '',
  repo_url: '',
  branch: 'main',
  subdir: '',
}

function summaryToDetail(kb: KbSummary): KbDetail {
  return { ...kb, last_commit: null, running: false }
}

export default function KbsPage() {
  const [kbs, setKbs] = useState<KbDetail[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [adminOpen, setAdminOpen] = useState(false)
  const [tokenInput, setTokenInput] = useState(() => api.getAdminToken())
  const [adminToken, setAdminToken] = useState(() => api.getAdminToken())
  const [formOpen, setFormOpen] = useState(false)
  const [form, setForm] = useState<KbCreateInput>(EMPTY_FORM)
  const [browseKb, setBrowseKb] = useState<string | null>(null)
  const [docs, setDocs] = useState<KbDocument[]>([])
  const [docsLoading, setDocsLoading] = useState(false)
  const [docError, setDocError] = useState<string | null>(null)
  const [openDoc, setOpenDoc] = useState<KbDocument | null>(null)
  const [page, setPage] = useState<KbDocumentPage | null>(null)
  const [pageLoading, setPageLoading] = useState(false)
  const [sourceView, setSourceView] = useState(false)
  const polling = useRef<Set<string>>(new Set())

  const refresh = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const list = await api.listKbs()
      // A single failing detail must not hide the whole list.
      const details = await Promise.all(
        list.map(async (kb) => {
          try {
            return { name: kb.name, detail: await api.getKb(kb.name), ok: true }
          } catch {
            return { name: kb.name, detail: summaryToDetail(kb), ok: false }
          }
        }),
      )
      setKbs(details.map(({ detail }) => detail))
      setError(null)
      for (const name of [...polling.current]) {
        const entry = details.find((d) => d.name === name)
        // A failed detail request must not look like a finished sync: keep polling.
        if (entry?.ok && !entry.detail.running) polling.current.delete(name)
      }
    } catch (e) {
      setError(String(e))
    } finally {
      if (!silent) setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  // Poll only while a sync triggered from this page is running; skip hidden tabs.
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (polling.current.size > 0 && !document.hidden) void refresh(true)
    }, 3000)
    return () => window.clearInterval(timer)
  }, [refresh])

  const saveToken = () => {
    const value = tokenInput.trim()
    api.setAdminToken(value)
    setAdminToken(value)
    setTokenInput(value)
    setNotice(value ? '管理员令牌已保存到当前标签页会话' : '管理员令牌已清除')
  }

  const create = async (e: FormEvent) => {
    e.preventDefault()
    if (!adminToken) {
      setAdminOpen(true)
      setError('请先输入管理员令牌')
      return
    }
    setBusy('create')
    setError(null)
    try {
      const created = await api.createKb(
        {
          ...form,
          name: form.name.trim(),
          description: form.description.trim(),
          repo_url: form.repo_url.trim(),
          branch: form.branch.trim() || 'main',
          subdir: form.subdir.trim(),
        },
        adminToken,
      )
      setForm(EMPTY_FORM)
      setFormOpen(false)
      setNotice(`已创建「${created.name}」，文档数为 0，还需点击「同步」才会导入文档`)
      await refresh()
    } catch (err) {
      setError(String(err))
    } finally {
      setBusy(null)
    }
  }

  const sync = async (name: string) => {
    if (!adminToken) {
      setAdminOpen(true)
      setError('请先输入管理员令牌')
      return
    }
    setBusy(name)
    setError(null)
    try {
      await api.syncKb(name, adminToken)
      polling.current.add(name)
      setNotice(`已触发「${name}」同步，正在刷新状态`)
      await refresh(true)
    } catch (err) {
      setError(String(err))
    } finally {
      setBusy(null)
    }
  }

  const setField = (key: keyof KbCreateInput, value: string) =>
    setForm((prev) => ({ ...prev, [key]: value }))

  const closeBrowse = () => {
    setBrowseKb(null)
    setDocs([])
    setOpenDoc(null)
    setPage(null)
    setDocError(null)
  }

  const toggleDocs = async (name: string) => {
    if (browseKb === name) {
      closeBrowse()
      return
    }
    setBrowseKb(name)
    setDocs([])
    setOpenDoc(null)
    setPage(null)
    setDocError(null)
    setDocsLoading(true)
    try {
      setDocs(await api.listDocuments(name))
    } catch (err) {
      setDocError(String(err))
    } finally {
      setDocsLoading(false)
    }
  }

  const loadPage = async (name: string, docId: string, offset: number) => {
    setPageLoading(true)
    setDocError(null)
    try {
      setPage(await api.readDocument(name, docId, offset, PAGE_LIMIT))
    } catch (err) {
      setDocError(String(err))
    } finally {
      setPageLoading(false)
    }
  }

  const openDocument = (name: string, doc: KbDocument) => {
    setOpenDoc(doc)
    setPage(null)
    void loadPage(name, doc.doc_id, 0)
  }

  return (
    <div className="mx-auto h-screen max-w-6xl overflow-y-auto px-4 py-6">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <button className="text-sm text-blue-600 hover:underline" onClick={() => navigate('/')}>
          &larr; 聊天
        </button>
        <h1 className="text-lg font-semibold">知识库</h1>
        <button
          className="rounded border border-gray-300 px-3 py-1 text-sm hover:bg-gray-100 disabled:opacity-50"
          disabled={loading}
          onClick={() => void refresh()}
        >
          {loading ? '刷新中...' : '刷新'}
        </button>
        <button
          className="rounded border border-gray-300 px-3 py-1 text-sm hover:bg-gray-100"
          onClick={() => setAdminOpen((v) => !v)}
        >
          管理员 {adminToken ? '· 已设置' : ''}
        </button>
        <button
          className="rounded bg-blue-600 px-3 py-1 text-sm text-white hover:bg-blue-700"
          onClick={() => setFormOpen((v) => !v)}
        >
          新建知识库
        </button>
      </div>

      {error && (
        <div className="mb-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}
      {notice && (
        <div className="mb-3 rounded border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-700">
          {notice}
        </div>
      )}

      {adminOpen && (
        <section className="mb-4 rounded-lg border border-gray-200 bg-white p-4">
          <h2 className="mb-1 text-sm font-semibold">管理员令牌（X-Admin-Token）</h2>
          <p className="mb-3 text-xs text-gray-500">
            只读浏览不需要令牌。新建与同步需要后端配置的 RAG_ADMIN_TOKEN；令牌仅保存在当前标签页的
            sessionStorage，关闭标签页即失效，不会写入前端代码包或 localStorage。
          </p>
          <div className="flex flex-wrap gap-2">
            <input
              type="password"
              autoComplete="off"
              className="w-72 rounded border border-gray-300 px-2 py-1 text-sm"
              placeholder="请输入管理员令牌"
              value={tokenInput}
              onChange={(e) => setTokenInput(e.target.value)}
            />
            <button
              className="rounded border border-gray-300 px-3 py-1 text-sm hover:bg-gray-100"
              onClick={saveToken}
            >
              保存
            </button>
            <button
              className="rounded border border-gray-300 px-3 py-1 text-sm hover:bg-gray-100"
              onClick={() => {
                setTokenInput('')
                api.setAdminToken('')
                setAdminToken('')
                setNotice('管理员令牌已清除')
              }}
            >
              清除
            </button>
          </div>
        </section>
      )}

      {formOpen && (
        <form onSubmit={create} className="mb-4 rounded-lg border border-gray-200 bg-white p-4">
          <h2 className="mb-3 text-sm font-semibold">新建知识库</h2>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="text-sm">
              名称
              <input
                required
                className="mt-1 w-full rounded border border-gray-300 px-2 py-1"
                value={form.name}
                onChange={(e) => setField('name', e.target.value)}
              />
            </label>
            <label className="text-sm">
              仓库地址
              <input
                required
                className="mt-1 w-full rounded border border-gray-300 px-2 py-1"
                placeholder="https://host/org/repo.git"
                value={form.repo_url}
                onChange={(e) => setField('repo_url', e.target.value)}
              />
            </label>
            <label className="text-sm md:col-span-2">
              简介
              <input
                required
                className="mt-1 w-full rounded border border-gray-300 px-2 py-1"
                placeholder="给模型看的简介，决定选库准确度"
                value={form.description}
                onChange={(e) => setField('description', e.target.value)}
              />
            </label>
            <label className="text-sm">
              分支
              <input
                className="mt-1 w-full rounded border border-gray-300 px-2 py-1"
                value={form.branch}
                onChange={(e) => setField('branch', e.target.value)}
              />
            </label>
            <label className="text-sm">
              子目录（可选）
              <input
                className="mt-1 w-full rounded border border-gray-300 px-2 py-1"
                placeholder="docs"
                value={form.subdir}
                onChange={(e) => setField('subdir', e.target.value)}
              />
            </label>
          </div>
          <p className="mt-2 text-xs text-gray-500">
            仓库地址仅接受 https / ssh / git 形式；本地目录需后端配置 RAG_LOCAL_ROOT。
            创建后文档数为 0，需再点击「同步」才会导入 .md / .pdf 文档。
          </p>
          <div className="mt-3 flex gap-2">
            <button
              type="submit"
              disabled={busy === 'create'}
              className="rounded bg-blue-600 px-3 py-1 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {busy === 'create' ? '创建中...' : '创建'}
            </button>
            <button
              type="button"
              className="rounded border border-gray-300 px-3 py-1 text-sm hover:bg-gray-100"
              onClick={() => setFormOpen(false)}
            >
              取消
            </button>
          </div>
        </form>
      )}

      <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-50 text-xs text-gray-500">
            <tr>
              <th className="px-3 py-2">名称</th>
              <th className="px-3 py-2">简介</th>
              <th className="px-3 py-2 text-right">文档数</th>
              <th className="px-3 py-2">最近同步</th>
              <th className="px-3 py-2">版本</th>
              <th className="px-3 py-2">状态 / 错误</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {kbs.map((kb) => (
              <Fragment key={kb.name}>
                <tr className="border-t border-gray-100 align-top">
                  <td className="whitespace-nowrap px-3 py-2 font-medium">{kb.name}</td>
                  <td className="max-w-56 px-3 py-2 text-gray-600">{kb.description}</td>
                  <td className="px-3 py-2 text-right">{kb.doc_count}</td>
                  <td className="whitespace-nowrap px-3 py-2">
                    {kb.synced_at ? fmtTime(kb.synced_at) : '未同步'}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 font-mono text-xs" title={kb.last_commit ?? ''}>
                    {kb.last_commit ? kb.last_commit.slice(0, 10) : '-'}
                  </td>
                  <td className="max-w-72 px-3 py-2">
                    {kb.running && <span className="mr-2 rounded bg-blue-50 px-2 py-0.5 text-xs text-blue-700">同步中</span>}
                    {!kb.running && !kb.last_error && kb.synced_at && (
                      <span className="rounded bg-green-50 px-2 py-0.5 text-xs text-green-700">正常</span>
                    )}
                    {kb.last_error && (
                      <span className="break-words text-red-600" title={kb.last_error}>
                        {kb.last_error}
                      </span>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2">
                    <div className="flex gap-1">
                      <button
                        className="rounded border border-gray-300 px-2 py-1 text-xs hover:bg-gray-100"
                        onClick={() => void toggleDocs(kb.name)}
                      >
                        {browseKb === kb.name ? '收起' : '文档'}
                      </button>
                      <button
                        className="rounded border border-gray-300 px-2 py-1 text-xs hover:bg-gray-100 disabled:opacity-50"
                        disabled={kb.running || busy === kb.name}
                        onClick={() => void sync(kb.name)}
                      >
                        {busy === kb.name ? '启动中...' : '同步'}
                      </button>
                    </div>
                  </td>
                </tr>
                {browseKb === kb.name && (
                  <tr className="border-t border-gray-100 bg-gray-50">
                    <td colSpan={7} className="px-4 py-3">
                      {docError && <div className="mb-2 text-sm text-red-600">{docError}</div>}
                      {docsLoading ? (
                        <div className="text-sm text-gray-400">加载文档列表...</div>
                      ) : docs.length === 0 && !docError ? (
                        <div className="text-sm text-gray-400">该知识库暂无文档，请先同步。</div>
                      ) : (
                        <div className="mb-3 flex flex-wrap gap-2">
                          {docs.map((doc) => (
                            <button
                              key={doc.doc_id}
                              className={`rounded border px-2 py-1 text-left text-xs ${
                                openDoc?.doc_id === doc.doc_id
                                  ? 'border-blue-400 bg-blue-50 text-blue-700'
                                  : 'border-gray-300 bg-white hover:bg-gray-100'
                              }`}
                              title={`${doc.title} (${doc.chars} 字符)`}
                              onClick={() => openDocument(kb.name, doc)}
                            >
                              {doc.path}
                            </button>
                          ))}
                        </div>
                      )}
                      {openDoc && (
                        <div className="rounded border border-gray-200 bg-white">
                          <div className="flex flex-wrap items-center gap-2 border-b border-gray-200 px-3 py-2 text-xs text-gray-500">
                            <span className="font-medium text-gray-700">{openDoc.path}</span>
                            <span>{page ? `${page.offset + 1} - ${page.offset + page.text.length} / ${page.total_chars} 字符` : ''}</span>
                            <button
                              className="rounded border border-gray-300 px-2 py-0.5 hover:bg-gray-100"
                              onClick={() => setSourceView((v) => !v)}
                            >
                              {sourceView ? '渲染' : '源码'}
                            </button>
                            <button
                              className="ml-auto rounded border border-gray-300 px-2 py-0.5 hover:bg-gray-100"
                              onClick={() => { setOpenDoc(null); setPage(null) }}
                            >
                              关闭
                            </button>
                          </div>
                          {pageLoading ? (
                            <div className="px-3 py-4 text-sm text-gray-400">加载正文...</div>
                          ) : page ? (
                            <>
                              {sourceView ? (
                                <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words px-3 py-3 text-xs text-gray-800">{page.text}</pre>
                              ) : (
                                <div className="prose prose-sm max-w-none prose-pre:bg-gray-900 max-h-96 overflow-auto px-3 py-3">
                                  <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
                                    {page.text}
                                  </ReactMarkdown>
                                </div>
                              )}
                              <div className="flex items-center gap-2 border-t border-gray-200 px-3 py-2">
                                <button
                                  className="rounded border border-gray-300 px-2 py-0.5 text-xs hover:bg-gray-100 disabled:opacity-40"
                                  disabled={page.offset === 0 || pageLoading}
                                  onClick={() => void loadPage(kb.name, openDoc.doc_id, Math.max(0, page.offset - PAGE_LIMIT))}
                                >
                                  上一页
                                </button>
                                <button
                                  className="rounded border border-gray-300 px-2 py-0.5 text-xs hover:bg-gray-100 disabled:opacity-40"
                                  disabled={!page.has_more || pageLoading}
                                  onClick={() => void loadPage(kb.name, openDoc.doc_id, page.offset + PAGE_LIMIT)}
                                >
                                  下一页
                                </button>
                                <span className="text-xs text-gray-400">{page.has_more ? '还有后续内容' : '已到末尾'}</span>
                              </div>
                            </>
                          ) : null}
                        </div>
                      )}
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
            {!loading && kbs.length === 0 && (
              <tr>
                <td colSpan={7} className="px-3 py-8 text-center text-gray-400">
                  暂无知识库
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

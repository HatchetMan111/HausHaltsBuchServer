import React from 'react'
import ReactDOM from 'react-dom/client'
import { createElement as h } from 'react'
import './styles.css'

const { useState, useEffect, useMemo, useCallback } = React

/* ------------------------------------------------------------------ API */
async function api(path, opts = {}) {
  const res = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  })
  if (!res.ok) {
    let detail = ''
    try { detail = (await res.json()).detail || '' } catch { /* ignore */ }
    throw new Error(detail || `HTTP ${res.status}`)
  }
  return res.json()
}

/* ------------------------------------------------------------------ Helpers */
const eur = (v) =>
  new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(Number(v) || 0)
const eurShort = (v) => {
  const n = Number(v) || 0
  if (Math.abs(n) >= 10000) return `${(n / 1000).toFixed(1).replace('.', ',')}k €`
  return eur(n)
}
const dateDE = (iso) => {
  if (!iso) return ''
  const [y, m, d] = iso.split('-')
  return `${d}.${m}.${y}`
}
const MONATE = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
  'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember']
const todayISO = () => new Date().toISOString().slice(0, 10)

const NAV = [
  { path: '/', label: 'Dashboard', ico: '📊' },
  { path: '/buchungen', label: 'Buchungen', ico: '📒' },
  { path: '/analyse', label: 'Analyse', ico: '📈' },
  { path: '/import', label: 'Import & Export', ico: '📥' },
  { path: '/verwaltung', label: 'Verwaltung', ico: '⚙️' },
]

/* ------------------------------------------------------------------ App */
export default function App() {
  const [route, setRoute] = useState(window.location.hash.replace('#', '') || '/')
  const [toast, setToast] = useState(null)

  const notify = useCallback((text, kind = 'ok') => {
    setToast({ text, kind })
    setTimeout(() => setToast(null), 3200)
  }, [])

  useEffect(() => {
    const onHash = () => setRoute(window.location.hash.replace('#', '') || '/')
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const navigate = (path) => { window.location.hash = path }

  const nav = useMemo(() => NAV.find((n) => n.path === route) || NAV[0], [route])

  return h(
    'div',
    { className: 'shell' },
    h(Sidebar, { route, navigate }),
    h(
      'main',
      { className: 'main' },
      route === '/' && h(Dashboard, { notify, navigate }),
      route === '/buchungen' && h(Buchungen, { notify }),
      route === '/analyse' && h(Analyse, { notify }),
      route === '/import' && h(ImportExport, { notify }),
      route === '/verwaltung' && h(Verwaltung, { notify }),
      h('div', { style: { marginTop: 40, textAlign: 'center', color: 'var(--text-faint)', fontSize: 11.5 } },
        `Haushaltsbuch · lokal · ${nav.label}`),
    ),
    toast && h('div', { className: `toast ${toast.kind}` }, toast.text),
  )
}

/* ------------------------------------------------------------------ Sidebar */
function Sidebar({ route, navigate }) {
  return h(
    'aside',
    { className: 'sidebar' },
    h(
      'div',
      { className: 'brand' },
      h('div', { className: 'brand-logo' }, '€'),
      h('div', { className: 'brand-text' },
        h('strong', null, 'Haushaltsbuch'),
        h('span', null, 'lokal. privat. übersichtlich.')),
    ),
    h(
      'nav',
      { className: 'nav' },
      h('div', { className: 'nav-label' }, 'Übersicht'),
      ...NAV.map((n) =>
        h('a', {
          key: n.path,
          href: `#${n.path}`,
          className: route === n.path ? 'active' : '',
          onClick: (e) => { e.preventDefault(); navigate(n.path) },
        }, h('span', { className: 'ico' }, n.ico), n.label),
      ),
    ),
    h('div', { className: 'sidebar-foot' },
      h('b', null, 'Alles bleibt bei dir'),
      h('br'),
      'Keine Cloud, kein Konto. Daten liegen in einer lokalen SQLite-Datei im Container.'),
  )
}

/* ------------------------------------------------------------------ Stat-Karte */
function Stat({ label, value, sub, tone, ico }) {
  return h(
    'div',
    { className: 'card stat' },
    h('div', { className: 'stat-label' }, ico ? h('span', null, ico) : null, label),
    h('div', { className: `stat-value ${tone || ''}` }, value),
    sub && h('div', { className: 'stat-sub' }, sub),
  )
}

/* ------------------------------------------------------------------ Dashboard */
function Dashboard({ notify, navigate }) {
  const [meta, setMeta] = useState({ jahre: [], monate: [] })
  const [year, setYear] = useState(null)
  const [month, setMonth] = useState(null)
  const [dash, setDash] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(async (y, m) => {
    setLoading(true); setError(null)
    try {
      const qs = new URLSearchParams()
      if (y) qs.set('year', y)
      if (m) qs.set('month', m)
      const [d] = await Promise.all([api(`/dashboard?${qs}`)])
      setDash(d)
    } catch (e) {
      setError(e.message)
    } finally { setLoading(false) }
  }, [])

  useEffect(() => {
    api('/meta').then((m) => {
      setMeta(m)
      const y = year || m.jahre[0] || new Date().getFullYear()
      setYear(y)
      load(y, month)
    }).catch((e) => { setError(e.message); setLoading(false) })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const waehle = (y, m) => { setYear(y); setMonth(m); load(y, m) }

  if (loading && !dash) return h('div', { className: 'center' }, h('div', { className: 'spinner' }), 'Lade Übersicht …')
  if (error) return h(FehlerBox, { error, onRetry: () => load(year, month) })

  const jahre = meta.jahre.length ? meta.jahre : [new Date().getFullYear()]
  const monate = meta.monate.map((m) => m.month)
  const maxKat = Math.max(1, ...dash.kategorien.map((k) => k.ausgaben))

  return h(
    React.Fragment,
    null,
    h(
      'div',
      { className: 'page-head' },
      h('div', null,
        h('h1', null, 'Übersicht'),
        h('p', null, year
          ? `${dash.anzahl} Buchungen im ${month ? MONATE[month - 1] + ' ' : ''}${year}`
          : 'Alle Buchungen')),
      h('div', { className: 'page-actions' },
        h('select', {
          className: 'input', style: { width: 118 },
          value: year || '', onChange: (e) => waehle(e.target.value || null, month),
        },
          h('option', { value: '' }, 'Alle Jahre'),
          ...jahre.map((y) => h('option', { key: y, value: y }, y))),
        h('select', {
          className: 'input', style: { width: 128 },
          value: month || '', onChange: (e) => waehle(year, e.target.value || null),
        },
          h('option', { value: '' }, 'Alle Monate'),
          ...MONATE.map((m, i) => h('option', { key: m, value: i + 1 }, m)).filter((_, i) => monate.includes(i + 1) || !monate.length)),
        h('button', { className: 'btn primary', onClick: () => navigate('/buchungen') }, '＋ Buchung'),
      ),
    ),
    h('div', { className: 'grid grid-4', style: { marginBottom: 16 } },
      h(Stat, {
        label: 'Einnahmen', value: eur(dash.einnahmen), ico: '⬆️',
        sub: 'Summe aller Einnahmen im Zeitraum', tone: 'pos',
      }),
      h(Stat, {
        label: 'Ausgaben', value: eur(dash.ausgaben), ico: '⬇️',
        sub: 'Summe aller Ausgaben im Zeitraum', tone: 'neg',
      }),
      h(Stat, {
        label: 'Überschuss', value: eur(dash.ueberschuss), ico: '⚖️',
        sub: `Sparquote ${dash.sparquote.toLocaleString('de-DE')}%`,
        tone: dash.ueberschuss >= 0 ? 'pos' : 'neg',
      }),
      h(Stat, {
        label: 'Kontostand', value: eur(dash.saldo_konten), ico: '🏦',
        sub: `${dash.konten.length} Konten · Saldo aus allen Buchungen`,
      }),
    ),
    h('div', { className: 'grid grid-1-2', style: { marginBottom: 16 } },
      h(
        'div',
        { className: 'card' },
        h('div', { className: 'card-title' },
          h('h2', null, 'Ausgaben nach Kategorie'),
          h('span', { className: 'hint' }, 'Monat / Zeitraum')),
        dash.kategorien.length
          ? h('div', { className: 'bar-list' },
            ...dash.kategorien.map((k) =>
              h('div', { key: k.id, className: 'bar-row' },
                h('div', { className: 'bar-name' },
                  h('span', { className: 'avatar-cat', style: { background: `${k.farbe}22` } }, k.icon),
                  h('span', { style: { overflow: 'hidden', textOverflow: 'ellipsis' } }, k.name)),
                h('div', { className: 'bar-track' },
                  h('div', {
                    className: 'bar-fill',
                    style: { width: `${Math.max(2, (k.ausgaben / maxKat) * 100)}%`, background: k.farbe },
                  })),
                h('div', { className: 'bar-amt' }, eurShort(k.ausgaben))),
            ))
          : h('div', { className: 'empty' }, h('span', { className: 'big' }, '🌱'),
            'Noch keine Ausgaben in diesem Zeitraum.'),
      ),
      h(
        'div',
        { className: 'card' },
        h('div', { className: 'card-title' }, h('h2', null, 'Monatsverlauf'),
          h('span', { className: 'hint' }, 'letzte 12 Monate')),
        h(MonatsChart, { data: dash.monatsverlauf }),
      ),
    ),
    h('div', { className: 'grid grid-1-2' },
      h(
        'div',
        { className: 'card' },
        h('div', { className: 'card-title' }, h('h2', null, 'Konten'),
          h('button', { className: 'btn sm', onClick: () => navigate('/verwaltung') }, 'verwalten')),
        h('div', { className: 'table-wrap' },
          h('table', null,
            h('thead', null, h('tr', null,
              h('th', null, 'Konto'), h('th', { className: 'num' }, 'Buchungen'),
              h('th', { className: 'num' }, 'Saldo'))),
            h('tbody', null, ...dash.konten.map((k) =>
              h('tr', { key: k.id },
                h('td', { className: 'strong' }, k.name),
                h('td', { className: 'num muted' }, k.anzahl),
                h('td', { className: `num strong ${k.saldo >= 0 ? 'pos-text' : 'neg-text'}` }, eur(k.saldo))))))),
      ),
      h(
        'div',
        { className: 'card' },
        h('div', { className: 'card-title' }, h('h2', null, 'Größte Empfänger'),
          h('span', { className: 'hint' }, 'Ausgaben im Zeitraum')),
        dash.top_empfaenger.length
          ? h('div', { className: 'bar-list' },
            ...dash.top_empfaenger.map((t) =>
              h('div', { key: t.name, className: 'bar-row', style: { gridTemplateColumns: '1fr 90px' } },
                h('div', { className: 'bar-name' }, h('span', { style: { overflow: 'hidden', textOverflow: 'ellipsis' } }, t.name)),
                h('div', { className: 'bar-amt' }, eurShort(t.summe)))))
          : h('div', { className: 'empty' }, 'Keine Daten.'),
      ),
    ),
  )
}

/* ------------------------------------------------------------------ Monats-Chart (SVG, ohne Extra-Lib) */
function MonatsChart({ data }) {
  if (!data || !data.length) return h('div', { className: 'empty' }, 'Kein Verlauf vorhanden.')
  const W = 520, H = 190, pad = 10
  const max = Math.max(1, ...data.flatMap((d) => [d.einnahmen, d.ausgaben]))
  const bw = (W - pad * 2) / data.length
  const y = (v) => H - pad - (v / max) * (H - pad * 2 - 16)
  return h(
    'div',
    { style: { overflowX: 'auto' } },
    h('svg', { viewBox: `0 0 ${W} ${H}`, width: '100%', height: 190, role: 'img' },
      h('line', { x1: pad, y1: H - pad, x2: W - pad, y2: H - pad, stroke: 'rgba(148,163,184,0.2)' }),
      ...data.map((d, i) => {
        const x = pad + i * bw
        const w = Math.max(3, bw * 0.32)
        return h('g', { key: d.monat },
          h('rect', {
            x: x + bw * 0.12, y: y(d.einnahmen), width: w, height: Math.max(2, H - pad - y(d.einnahmen)),
            rx: 3, fill: '#34d399', opacity: 0.9,
          }),
          h('rect', {
            x: x + bw * 0.12 + w + 3, y: y(d.ausgaben), width: w, height: Math.max(2, H - pad - y(d.ausgaben)),
            rx: 3, fill: '#f87171', opacity: 0.9,
          }),
          h('text', {
            x: x + bw / 2, y: H - 1, textAnchor: 'middle',
            fontSize: 8.5, fill: '#64748b',
          }, d.monat.slice(5)),
        )
      })),
    h('div', { className: 'btn-row', style: { marginTop: 6, fontSize: 11.5, color: 'var(--text-dim)' } },
      h('span', null, '🟩 Einnahmen'), h('span', null, '🟥 Ausgaben')),
  )
}

/* ------------------------------------------------------------------ Fehler */
function FehlerBox({ error, onRetry }) {
  return h('div', { className: 'card', style: { borderColor: 'rgba(248,113,113,0.4)' } },
    h('div', { style: { fontSize: 26, marginBottom: 6 } }, '⚠️'),
    h('h2', { style: { margin: '0 0 6px' } }, 'Backend nicht erreichbar'),
    h('p', { className: 'muted', style: { fontSize: 13, lineHeight: 1.6 } },
      'Die API hat mit einem Fehler geantwortet. Prüfe im Container:'),
    h('pre', {
      style: {
        background: 'rgba(3,7,18,0.6)', padding: '10px 12px', borderRadius: 10,
        fontSize: 11.5, overflow: 'auto', color: '#fca5a5',
      },
    }, error),
    onRetry && h('button', { className: 'btn', style: { marginTop: 10 }, onClick: onRetry }, 'Erneut versuchen'),
  )
}

/* ------------------------------------------------------------------ Buchungen */
function Buchungen({ notify }) {
  const [meta, setMeta] = useState({ jahre: [], monate: [] })
  const [filter, setFilter] = useState({ year: null, month: null, typ: '', q: '', konto_id: '' })
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(null)
  const [konten, setKonten] = useState([])
  const [kategorien, setKategorien] = useState([])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const qs = new URLSearchParams()
      if (filter.year) qs.set('year', filter.year)
      if (filter.month) qs.set('month', filter.month)
      if (filter.typ) qs.set('typ', filter.typ)
      if (filter.q) qs.set('q', filter.q)
      if (filter.konto_id) qs.set('konto_id', filter.konto_id)
      const [data, k, ka] = await Promise.all([
        api(`/buchungen?${qs}`), api('/konten'), api('/kategorien'),
      ])
      setRows(data.buchungen)
      setKonten(k); setKategorien(ka)
    } catch (e) { notify(e.message, 'err') } finally { setLoading(false) }
  }, [filter, notify])

  useEffect(() => {
    api('/meta').then((m) => {
      setMeta(m)
      setFilter((f) => ({ ...f, year: f.year || m.jahre[0] || null }))
    }).catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => { load() }, [load])

  const save = async (payload, id) => {
    try {
      if (id) await api(`/buchungen/${id}`, { method: 'PUT', body: payload })
      else await api('/buchungen', { method: 'POST', body: payload })
      setEditing(null)
      notify(id ? 'Buchung aktualisiert' : 'Buchung gespeichert')
      load()
    } catch (e) { notify(e.message, 'err') }
  }

  const del = async (id) => {
    if (!window.confirm('Buchung wirklich löschen?')) return
    try { await api(`/buchungen/${id}`, { method: 'DELETE' }); notify('Buchung gelöscht'); load() }
    catch (e) { notify(e.message, 'err') }
  }

  return h(
    React.Fragment,
    null,
    h('div', { className: 'page-head' },
      h('div', null, h('h1', null, 'Buchungen'),
        h('p', null, 'Alle Einnahmen und Ausgaben – filterbar und editierbar.')),
      h('div', { className: 'page-actions' },
        h('a', { className: 'btn', href: '#/import', onClick: (e) => { e.preventDefault(); window.location.hash = '/import' } }, '📥 CSV-Import'),
        h('button', { className: 'btn primary', onClick: () => setEditing({ neu: true }) }, '＋ Buchung')),
    ),
    h('div', { className: 'card', style: { marginBottom: 16 } },
      h('div', { className: 'btn-row', style: { gap: 10 } },
        h('input', {
          className: 'input', placeholder: '🔍 Suche in Beschreibung …', style: { maxWidth: 260 },
          value: filter.q, onChange: (e) => setFilter({ ...filter, q: e.target.value }),
        }),
        h('select', {
          className: 'input', style: { width: 130 }, value: filter.year || '',
          onChange: (e) => setFilter({ ...filter, year: e.target.value || null, month: null }),
        },
          h('option', { value: '' }, 'Alle Jahre'),
          ...(meta.jahre.length ? meta.jahre : [new Date().getFullYear()]).map((y) => h('option', { key: y, value: y }, y))),
        h('select', {
          className: 'input', style: { width: 130 }, value: filter.month || '',
          onChange: (e) => setFilter({ ...filter, month: e.target.value || null }),
        },
          h('option', { value: '' }, 'Alle Monate'),
          ...MONATE.map((m, i) => h('option', { key: m, value: i + 1 }, m))),
        h('select', {
          className: 'input', style: { width: 120 }, value: filter.typ,
          onChange: (e) => setFilter({ ...filter, typ: e.target.value }),
        },
          h('option', { value: '' }, 'Alle Typen'),
          h('option', { value: 'einnahme' }, 'Einnahmen'),
          h('option', { value: 'ausgabe' }, 'Ausgaben')),
        h('select', {
          className: 'input', style: { width: 140 }, value: filter.konto_id,
          onChange: (e) => setFilter({ ...filter, konto_id: e.target.value }),
        },
          h('option', { value: '' }, 'Alle Konten'),
          ...konten.map((k) => h('option', { key: k.id, value: k.id }, k.name))),
        h('button', { className: 'btn sm', onClick: () => setFilter({ year: null, month: null, typ: '', q: '', konto_id: '' }) }, 'Zurücksetzen'),
      ),
    ),
    h('div', { className: 'card' },
      loading
        ? h('div', { className: 'center' }, h('div', { className: 'spinner' }), 'Lade Buchungen …')
        : rows.length === 0
          ? h('div', { className: 'empty' }, h('span', { className: 'big' }, '🗒️'), 'Keine Buchungen gefunden.')
          : h('div', { className: 'table-wrap' },
            h('table', null,
              h('thead', null, h('tr', null,
                h('th', null, 'Datum'), h('th', null, 'Beschreibung'),
                h('th', null, 'Kategorie'), h('th', null, 'Konto'),
                h('th', { className: 'num' }, 'Betrag'), h('th', null, ''))),
              h('tbody', null, ...rows.map((b) =>
                h('tr', { key: b.id },
                  h('td', { className: 'muted', style: { whiteSpace: 'nowrap' } }, dateDE(b.datum)),
                  h('td', null,
                    h('div', { className: 'strong', style: { marginBottom: 2 } }, b.beschreibung || '–'),
                    (b.art || b.gegen_iban) && h('div', { className: 'faint' },
                      [b.art, b.gegen_iban].filter(Boolean).join(' · '))),
                  h('td', null, b.kategorie
                    ? h('span', { className: 'chip', style: { background: `${b.kategorie_farbe || '#6366f1'}1f`, color: b.kategorie_farbe || '#c7d2fe' } },
                      `${b.kategorie_icon || '•'} ${b.kategorie}`)
                    : h('span', { className: 'faint' }, '–')),
                  h('td', { className: 'muted' }, b.konto || '–'),
                  h('td', { className: `num strong ${b.typ === 'einnahme' ? 'pos-text' : 'neg-text'}` },
                    `${b.typ === 'einnahme' ? '+' : '−'}${eur(b.betrag)}`),
                  h('td', { style: { textAlign: 'right', whiteSpace: 'nowrap' } },
                    h('button', { className: 'btn sm', onClick: () => setEditing(b), title: 'Bearbeiten' }, '✏️'),
                    ' ',
                    h('button', { className: 'btn sm danger', onClick: () => del(b.id), title: 'Löschen' }, '🗑️'))),
              ))),
      ),
    ),
    editing && h(BuchungModal, {
      data: editing.neu ? null : editing,
      konten, kategorien,
      onClose: () => setEditing(null),
      onSave: (payload) => save(payload, editing.neu ? null : editing.id),
    }),
  )
}

/* ------------------------------------------------------------------ Buchungs-Modal */
function BuchungModal({ data, konten, kategorien, onClose, onSave }) {
  const [form, setForm] = useState(() => ({
    datum: data?.datum || todayISO(),
    typ: data?.typ || 'ausgabe',
    betrag: data ? String(data.betrag).replace('.', ',') : '',
    beschreibung: data?.beschreibung || '',
    kategorie_id: data?.kategorie_id || '',
    konto_id: data?.konto_id || (konten[0]?.id ?? ''),
    gegen_iban: data?.gegen_iban || '',
    notiz: data?.notiz || '',
    art: data?.art || 'Manuell',
    manually_edit: data?.manually_edit ? true : false,
  }))
  const [saving, setSaving] = useState(false)
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }))

  const submit = async (e) => {
    e.preventDefault()
    const betrag = parseFloat(String(form.betrag).replace(/\./g, '').replace(',', '.'))
    if (!form.beschreibung.trim() || !isFinite(betrag)) return
    setSaving(true)
    try {
      await onSave({
        ...form,
        datum: form.datum,
        betrag,
        kategorie_id: form.kategorie_id ? Number(form.kategorie_id) : null,
        konto_id: form.konto_id ? Number(form.konto_id) : null,
      })
    } finally { setSaving(false) }
  }

  const vorschau = (() => {
    const b = parseFloat(String(form.betrag).replace(/\./g, '').replace(',', '.'))
    return isFinite(b) ? eur(b) : '–'
  })()

  return h('div', {
    className: 'overlay',
    onMouseDown: (e) => { if (e.target === e.currentTarget) onClose() },
  },
    h('form', { className: 'modal', onSubmit: submit },
      h('h2', null, data ? 'Buchung bearbeiten' : 'Neue Buchung'),
      h('div', { className: 'sub' }, 'Einnahme oder Ausgabe erfassen – Felder mit * sind Pflicht.'),
      h('div', { className: 'grid grid-2' },
        h('label', { className: 'field' }, h('span', null, 'Datum *'),
          h('input', { className: 'input', type: 'date', value: form.datum, onChange: (e) => set('datum', e.target.value), required: true })),
        h('label', { className: 'field' }, h('span', null, 'Typ'),
          h('select', { className: 'input', value: form.typ, onChange: (e) => set('typ', e.target.value) },
            h('option', { value: 'ausgabe' }, '↘ Ausgabe'),
            h('option', { value: 'einnahme' }, '↗ Einnahme'))),
        h('label', { className: 'field' }, h('span', null, `Betrag * (Vorschau: ${vorschau})`),
          h('input', {
            className: 'input', value: form.betrag, inputMode: 'decimal',
            placeholder: '1.234,56', onChange: (e) => set('betrag', e.target.value), required: true,
          })),
        h('label', { className: 'field' }, h('span', null, 'Kategorie'),
          h('select', { className: 'input', value: form.kategorie_id, onChange: (e) => set('kategorie_id', e.target.value) },
            h('option', { value: '' }, '– automatisch –'),
            ...kategorien.map((k) => h('option', { key: k.id, value: k.id }, `${k.icon} ${k.name}`)))),
      ),
      h('label', { className: 'field' }, h('span', null, 'Beschreibung *'),
        h('input', {
          className: 'input', value: form.beschreibung, placeholder: 'z. B. REWE SAGT DANKE',
          onChange: (e) => set('beschreibung', e.target.value), required: true,
        })),
      h('div', { className: 'grid grid-2' },
        h('label', { className: 'field' }, h('span', null, 'Konto'),
          h('select', { className: 'input', value: form.konto_id, onChange: (e) => set('konto_id', e.target.value) },
            h('option', { value: '' }, '– kein Konto –'),
            ...konten.map((k) => h('option', { key: k.id, value: k.id }, k.name)))),
        h('label', { className: 'field' }, h('span', null, 'Gegen-IBAN'),
          h('input', {
            className: 'input', value: form.gegen_iban, placeholder: 'DE…',
            onChange: (e) => set('gegen_iban', e.target.value),
          })),
      ),
      h('label', { className: 'field' }, h('span', null, 'Notiz'),
        h('input', {
          className: 'input', value: form.notiz, placeholder: 'optional',
          onChange: (e) => set('notiz', e.target.value),
        })),
      h('label', { className: 'btn-row', style: { fontSize: 12.5, color: 'var(--text-dim)', gap: 8 } },
        h('input', {
          type: 'checkbox', checked: form.manually_edit,
          onChange: (e) => set('manually_edit', e.target.checked),
        }),
        'Als manuell gepflegt markieren (schützt vor Auto-Kategorisierung)'),
      h('div', { className: 'modal-foot' },
        h('button', { type: 'button', className: 'btn', onClick: onClose }, 'Abbrechen'),
        h('button', { type: 'submit', className: 'btn primary', disabled: saving },
          saving ? 'Speichert …' : 'Speichern')),
    ),
  )
}

/* ------------------------------------------------------------------ Analyse */
function Analyse({ notify }) {
  const [meta, setMeta] = useState({ jahre: [] })
  const [year, setYear] = useState(null)
  const [compare, setCompare] = useState('')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api('/meta').then((m) => {
      setMeta(m)
      setYear(m.jahre[0] || new Date().getFullYear())
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (!year) return
    setLoading(true)
    const qs = new URLSearchParams({ year })
    if (compare) qs.set('compare_year', compare)
    api(`/analyse?${qs}`).then(setData).catch((e) => notify(e.message, 'err')).finally(() => setLoading(false))
  }, [year, compare, notify])

  if (loading && !data) return h('div', { className: 'center' }, h('div', { className: 'spinner' }), 'Analysiere …')
  if (!data) return h('div', { className: 'empty' }, 'Keine Daten.')

  const cur = data.current
  const prev = data.previous
  const maxKat = Math.max(1, ...cur.kategorien.map((k) => k.ausgaben))
  const jahre = meta.jahre.length ? meta.jahre : [new Date().getFullYear()]

  return h(
    React.Fragment,
    null,
    h('div', { className: 'page-head' },
      h('div', null, h('h1', null, 'Analyse'), h('p', null, 'Jahresvergleich, Sparquote und Monatsverteilung.')),
      h('div', { className: 'page-actions' },
        h('select', {
          className: 'input', style: { width: 120 }, value: year || '',
          onChange: (e) => setYear(e.target.value || null),
        }, ...jahre.map((y) => h('option', { key: y, value: y }, y))),
        h('span', { className: 'faint' }, 'vs.'),
        h('select', {
          className: 'input', style: { width: 120 }, value: compare,
          onChange: (e) => setCompare(e.target.value),
        },
          h('option', { value: '' }, 'kein Vergleich'),
          ...jahre.filter((y) => y !== year).map((y) => h('option', { key: y, value: y }, y)))),
    ),
    h('div', { className: 'grid grid-3', style: { marginBottom: 16 } },
      h(Stat, { label: `Einnahmen ${year}`, value: eur(cur.einnahmen), tone: 'pos', ico: '⬆️', sub: `${cur.anzahl} Buchungen` }),
      h(Stat, { label: `Ausgaben ${year}`, value: eur(cur.ausgaben), tone: 'neg', ico: '⬇️', sub: `Sparquote ${cur.sparquote.toLocaleString('de-DE')}%` }),
      h(Stat, {
        label: 'Überschuss', value: eur(cur.ueberschuss), tone: cur.ueberschuss >= 0 ? 'pos' : 'neg', ico: '⚖️',
        sub: prev ? `${data.deltas.ueberschuss >= 0 ? '+' : ''}${eur(data.deltas.ueberschuss)} zum Vorjahr` : 'kein Vergleich gewählt',
      }),
    ),
    h('div', { className: 'grid grid-1-2' },
      h('div', { className: 'card' },
        h('div', { className: 'card-title' }, h('h2', null, 'Ausgaben je Kategorie'),
          h('span', { className: 'hint' }, String(year))),
        cur.kategorien.length
          ? h('div', { className: 'bar-list' }, ...cur.kategorien.map((k) =>
            h('div', { key: k.name, className: 'bar-row' },
              h('div', { className: 'bar-name' },
                h('span', { className: 'avatar-cat', style: { background: `${k.farbe}22` } }, k.icon),
                k.name),
              h('div', { className: 'bar-track' },
                h('div', { className: 'bar-fill', style: { width: `${Math.max(2, k.ausgaben / maxKat * 100)}%`, background: k.farbe } })),
              h('div', { className: 'bar-amt' }, eurShort(k.ausgaben)))))
          : h('div', { className: 'empty' }, 'Keine Ausgaben.')),
      h('div', { className: 'card' },
        h('div', { className: 'card-title' }, h('h2', null, 'Monatsvergleich'),
          h('span', { className: 'hint' }, 'Einnahmen vs. Ausgaben')),
        h(MonatsChart, { data: cur.monate.map((m) => ({ monat: `${year}-${String(m.monat).padStart(2, '0')}`, einnahmen: m.einnahmen, ausgaben: m.ausgaben })) }),
      ),
    ),
    prev && h('div', { className: 'card', style: { marginTop: 16 } },
      h('div', { className: 'card-title' }, h('h2', null, `Vergleich ${year} vs. ${compare}`)),
      h('div', { className: 'table-wrap' },
        h('table', null,
          h('thead', null, h('tr', null,
            h('th', null, 'Kennzahl'), h('th', { className: 'num' }, String(year)),
            h('th', { className: 'num' }, String(compare)), h('th', { className: 'num' }, 'Differenz'))),
          h('tbody', null,
            ...[['Einnahmen', cur.einnahmen, prev.einnahmen],
              ['Ausgaben', cur.ausgaben, prev.ausgaben],
              ['Überschuss', cur.ueberschuss, prev.ueberschuss],
              ['Sparquote (%)', cur.sparquote, prev.sparquote]].map(([label, a, b]) =>
              h('tr', { key: label },
                h('td', { className: 'strong' }, label),
                h('td', { className: 'num' }, label.includes('(%)') ? a.toLocaleString('de-DE') + '%' : eur(a)),
                h('td', { className: 'num' }, label.includes('(%)') ? b.toLocaleString('de-DE') + '%' : eur(b)),
                h('td', { className: `num ${a - b >= 0 ? 'pos-text' : 'neg-text'}` },
                  `${a - b >= 0 ? '+' : '−'}${label.includes('(%)') ? Math.abs(a - b).toLocaleString('de-DE') + '%' : eur(Math.abs(a - b))}`))))),
      ),
    ),
  )
}

/* ------------------------------------------------------------------ Import & Export */
function ImportExport({ notify }) {
  const [konten, setKonten] = useState([])
  const [konto, setKonto] = useState('')
  const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [dupe, setDupe] = useState(null)

  useEffect(() => { api('/konten').then(setKonten).catch(() => {}) }, [])

  const doImport = async () => {
    if (!file) return
    setBusy(true); setResult(null)
    try {
      const fd = new FormData()
      fd.append('datei', file)
      const qs = konto ? `?konto_id=${konto}` : ''
      const res = await fetch(`/api/import${qs}`, { method: 'POST', body: fd })
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`)
      const data = await res.json()
      setResult(data)
      notify(`${data.importiert} Buchungen importiert`)
    } catch (e) { notify(e.message, 'err') } finally { setBusy(false) }
  }

  const checkDupes = async () => {
    try { const d = await api('/duplikate'); setDupe(d.duplikate) } catch (e) { notify(e.message, 'err') }
  }

  return h(
    React.Fragment,
    null,
    h('div', { className: 'page-head' },
      h('div', null, h('h1', null, 'Import & Export'),
        h('p', null, 'Bank-CSV einlesen, Buchungen exportieren – alles lokal.')),
    ),
    h('div', { className: 'grid grid-2' },
      h('div', { className: 'card' },
        h('div', { className: 'card-title' }, h('h2', null, '📥 CSV-Import'),
          h('span', { className: 'hint' }, 'Semikolon oder Komma')),
        h('p', { className: 'muted', style: { fontSize: 12.5, lineHeight: 1.6, marginTop: 0 } },
          'Unterstützt deutsche Bank-Formate (Sparkasse, ING, Comdirect, Volksbank …). Beträge wie 1.234,56 € und Datum 01.12.2024 werden automatisch erkannt. Die Zuordnung erfolgt über die Schlüsselwörter in der Verwaltung.'),
        h('label', { className: 'field' }, h('span', null, 'Ziel-Konto (optional)'),
          h('select', { className: 'input', value: konto, onChange: (e) => setKonto(e.target.value) },
            h('option', { value: '' }, '– zuordnen per Standard –'),
            ...konten.map((k) => h('option', { key: k.id, value: k.id }, k.name)))),
        h('div', {
          className: 'card',
          style: {
            borderStyle: 'dashed', textAlign: 'center', padding: '26px 16px',
            background: 'rgba(99,102,241,0.05)',
          },
        },
          h('div', { style: { fontSize: 28, marginBottom: 8 } }, '📄'),
          file
            ? h('div', { style: { marginBottom: 10 } },
              h('div', { className: 'strong' }, file.name),
              h('div', { className: 'faint' }, `${(file.size / 1024).toFixed(1)} KB`))
            : h('div', { className: 'muted', style: { fontSize: 13, marginBottom: 10 } }, 'CSV-Datei auswählen'),
          h('input', {
            type: 'file', accept: '.csv,text/csv',
            onChange: (e) => { setFile(e.target.files?.[0] || null); setResult(null) },
          }),
        ),
        h('div', { className: 'btn-row', style: { marginTop: 14 } },
          h('button', { className: 'btn primary', disabled: !file || busy, onClick: doImport },
            busy ? 'Importiere …' : 'Import starten'),
          file && h('button', { className: 'btn', onClick: () => { setFile(null); setResult(null) } }, 'Datei entfernen')),
        result && h('div', {
          className: 'card', style: { marginTop: 14, background: 'rgba(52,211,153,0.08)', borderColor: 'rgba(52,211,153,0.3)' },
        },
          h('div', { className: 'strong', style: { marginBottom: 6 } }, 'Import abgeschlossen'),
          h('div', { className: 'faint', style: { lineHeight: 1.8 } },
            `✅ ${result.importiert} importiert · ⏭️ ${result.uebersprungen} Duplikate · ⚠️ ${result.fehler} übersprungen`),
          result.eigene_iban && h('div', { className: 'faint' }, `Erkannte eigene IBAN: ${result.eigene_iban}`),
        ),
      ),
      h('div', { className: 'card' },
        h('div', { className: 'card-title' }, h('h2', null, '📤 Export & Kontrolle')),
        h('p', { className: 'muted', style: { fontSize: 12.5, lineHeight: 1.6, marginTop: 0 } },
          'Export im deutschen Format (Semikolon, Komma als Dezimaltrenner) – direkt in Excel oder LibreOffice öffnen. Der Export kann später wieder importiert werden.'),
        h('div', { className: 'btn-row', style: { marginBottom: 12 } },
          h('a', { className: 'btn primary', href: '/api/export' }, 'Alle Buchungen exportieren'),
          h('a', { className: 'btn', href: `/api/buchungen?export=true&year=${new Date().getFullYear()}` },
            `${new Date().getFullYear()} exportieren`)),
        h('div', { className: 'btn-row' },
          h('button', { className: 'btn', onClick: checkDupes }, 'Duplikate prüfen')),
        dupe && h('div', { style: { marginTop: 12 } },
          dupe.length === 0
            ? h('div', { className: 'faint' }, 'Keine doppelten Buchungen gefunden.')
            : h('div', { className: 'table-wrap' },
              h('table', null,
                h('thead', null, h('tr', null,
                  h('th', null, 'Datum'), h('th', null, 'Beschreibung'), h('th', { className: 'num' }, 'Betrag'), h('th', { className: 'num' }, 'Anzahl'))),
                h('tbody', null, ...dupe.map((d, i) =>
                  h('tr', { key: i },
                    h('td', null, dateDE(d.datum)), h('td', null, d.beschreibung),
                    h('td', { className: 'num' }, eur(d.betrag)),
                    h('td', { className: 'num' }, d.n)))))),
        ),
      ),
    ),
  )
}

/* ------------------------------------------------------------------ Verwaltung */
function Verwaltung({ notify }) {
  const [tab, setTab] = useState('konten')
  const [konten, setKonten] = useState([])
  const [kategorien, setKategorien] = useState([])
  const [keywords, setKeywords] = useState([])
  const [system, setSystem] = useState(null)

  const loadAll = useCallback(async () => {
    try {
      const [k, ka, kw, sy] = await Promise.all([
        api('/konten'), api('/kategorien'), api('/keywords'), api('/system'),
      ])
      setKonten(k); setKategorien(ka); setKeywords(kw); setSystem(sy)
    } catch (e) { notify(e.message, 'err') }
  }, [notify])

  useEffect(() => { loadAll() }, [loadAll])

  const refresh = async (fn, msg) => {
    try { await fn(); await loadAll(); notify(msg) } catch (e) { notify(e.message, 'err') }
  }

  return h(
    React.Fragment,
    null,
    h('div', { className: 'page-head' },
      h('div', null, h('h1', null, 'Verwaltung'),
        h('p', null, 'Konten, Kategorien, Auto-Regeln und Systemstatus.')),
    ),
    h('div', { className: 'seg', style: { marginBottom: 16 } },
      ...[['konten', 'Konten'], ['kategorien', 'Kategorien'], ['regeln', 'Auto-Regeln'], ['system', 'System']]
        .map(([key, label]) =>
          h('button', { key, className: tab === key ? 'on' : '', onClick: () => setTab(key) }, label))),
    tab === 'konten' && h(KontenPanel, { konten, refresh }),
    tab === 'kategorien' && h(KategorienPanel, { kategorien, refresh }),
    tab === 'regeln' && h(RegelnPanel, { keywords, kategorien, refresh }),
    tab === 'system' && h(SystemPanel, { system }),
  )
}

function KontenPanel({ konten, refresh }) {
  const [form, setForm] = useState({ name: '', beschreibung: '', iban: '' })
  const [edit, setEdit] = useState(null)
  return h('div', { className: 'grid grid-1-2' },
    h('div', { className: 'card' },
      h('div', { className: 'card-title' }, h('h2', null, 'Konten'),
        h('span', { className: 'hint' }, `${konten.length} angelegt`)),
      h('div', { className: 'table-wrap' },
        h('table', null,
          h('thead', null, h('tr', null,
            h('th', null, 'Name'), h('th', null, 'IBAN'), h('th', { className: 'num' }, 'Saldo'), h('th', null, ''))),
          h('tbody', null, ...konten.map((k) =>
            h('tr', { key: k.id },
              h('td', null, h('div', { className: 'strong' }, k.name),
                k.beschreibung && h('div', { className: 'faint' }, k.beschreibung)),
              h('td', { className: 'muted', style: { fontSize: 12 } }, k.iban || '–'),
              h('td', { className: `num ${k.saldo >= 0 ? 'pos-text' : 'neg-text'}` }, eur(k.saldo)),
              h('td', null,
                h('button', { className: 'btn sm', onClick: () => setEdit(k) }, '✏️'), ' ',
                h('button', {
                  className: 'btn sm danger',
                  onClick: () => { if (confirm('Konto löschen? Buchungen bleiben erhalten.')) refresh(() => api(`/konten/${k.id}`, { method: 'DELETE' }), 'Konto gelöscht') },
                }, '🗑️')))))),
      ),
    ),
    h('div', { className: 'card' },
      h('div', { className: 'card-title' }, h('h2', null, edit ? 'Konto bearbeiten' : 'Neues Konto')),
      h('form', {
        onSubmit: (e) => {
          e.preventDefault()
          refresh(
            () => api(edit ? `/konten/${edit.id}` : '/konten', {
              method: edit ? 'PUT' : 'POST',
              body: { ...form, ...(edit ? { id: edit.id } : {}) },
            }),
            edit ? 'Konto aktualisiert' : 'Konto angelegt')
          setForm({ name: '', beschreibung: '', iban: '' }); setEdit(null)
        },
      },
        h('label', { className: 'field' }, h('span', null, 'Name *'),
          h('input', { className: 'input', value: form.name, required: true, onChange: (e) => setForm({ ...form, name: e.target.value }), placeholder: 'Girokonto' })),
        h('label', { className: 'field' }, h('span', null, 'Beschreibung'),
          h('input', { className: 'input', value: form.beschreibung, onChange: (e) => setForm({ ...form, beschreibung: e.target.value }), placeholder: 'Hauptkonto' })),
        h('label', { className: 'field' }, h('span', null, 'IBAN'),
          h('input', { className: 'input', value: form.iban, onChange: (e) => setForm({ ...form, iban: e.target.value }), placeholder: 'DE00 …' })),
        h('div', { className: 'btn-row' },
          h('button', { className: 'btn primary', type: 'submit' }, edit ? 'Speichern' : 'Anlegen'),
          edit && h('button', { className: 'btn', type: 'button', onClick: () => { setEdit(null); setForm({ name: '', beschreibung: '', iban: '' }) } }, 'Abbrechen')),
      ),
    ),
  )
}

function KategorienPanel({ kategorien, refresh }) {
  const [form, setForm] = useState({ name: '', art: 'ausgabe', icon: '📦', farbe: '#6366f1' })
  const [edit, setEdit] = useState(null)
  const farben = ['#22c55e', '#f97316', '#ef4444', '#0ea5e9', '#8b5cf6', '#eab308', '#14b8a6', '#ec4899', '#a855f7', '#64748b']
  return h('div', { className: 'grid grid-1-2' },
    h('div', { className: 'card' },
      h('div', { className: 'card-title' }, h('h2', null, 'Kategorien'),
        h('span', { className: 'hint' }, `${kategorien.length} gesamt`)),
      h('div', { className: 'table-wrap' },
        h('table', null,
          h('thead', null, h('tr', null,
            h('th', null, 'Kategorie'), h('th', null, 'Typ'), h('th', null, ''))),
          h('tbody', null, ...kategorien.map((k) =>
            h('tr', { key: k.id },
              h('td', null,
                h('span', { className: 'avatar-cat', style: { background: `${k.farbe}22`, marginRight: 8 } }, k.icon),
                h('span', { className: 'strong' }, k.name)),
              h('td', null, h('span', { className: `chip ${k.art === 'einnahme' ? 'einnahme' : 'ausgabe'}` }, k.art === 'beide' ? 'beide' : k.art === 'einnahme' ? 'Einnahme' : 'Ausgabe')),
              h('td', null,
                h('button', { className: 'btn sm', onClick: () => setEdit(k) }, '✏️'), ' ',
                h('button', {
                  className: 'btn sm danger',
                  onClick: () => { if (confirm('Kategorie löschen? Buchungen behalten den alten Status.')) refresh(() => api(`/kategorien/${k.id}`, { method: 'DELETE' }), 'Kategorie gelöscht') },
                }, '🗑️')))))),
      ),
    ),
    h('div', { className: 'card' },
      h('div', { className: 'card-title' }, h('h2', null, edit ? 'Kategorie bearbeiten' : 'Neue Kategorie')),
      h('form', {
        onSubmit: (e) => {
          e.preventDefault()
          refresh(
            () => api(edit ? `/kategorien/${edit.id}` : '/kategorien', {
              method: edit ? 'PUT' : 'POST',
              body: { ...form, ...(edit ? { id: edit.id } : {}) },
            }),
            edit ? 'Kategorie aktualisiert' : 'Kategorie angelegt')
          setForm({ name: '', art: 'ausgabe', icon: '📦', farbe: '#6366f1' }); setEdit(null)
        },
      },
        h('div', { className: 'grid grid-2' },
          h('label', { className: 'field' }, h('span', null, 'Name *'),
            h('input', { className: 'input', value: form.name, required: true, onChange: (e) => setForm({ ...form, name: e.target.value }) })),
          h('label', { className: 'field' }, h('span', null, 'Typ'),
            h('select', { className: 'input', value: form.art, onChange: (e) => setForm({ ...form, art: e.target.value }) },
              h('option', { value: 'ausgabe' }, 'Ausgabe'),
              h('option', { value: 'einnahme' }, 'Einnahme'),
              h('option', { value: 'beide' }, 'Beide'))),
          h('label', { className: 'field' }, h('span', null, 'Icon'),
            h('input', { className: 'input', value: form.icon, maxLength: 4, onChange: (e) => setForm({ ...form, icon: e.target.value }) })),
          h('div', null,
            h('span', { style: { fontSize: 11.5, color: 'var(--text-dim)', display: 'block', marginBottom: 6 } }, 'Farbe'),
            h('div', { className: 'btn-row', style: { gap: 5 } },
              ...farben.map((f) => h('button', {
                key: f, type: 'button',
                style: {
                  width: 24, height: 24, borderRadius: 8, background: f, cursor: 'pointer',
                  border: form.farbe === f ? '2px solid #fff' : '2px solid transparent',
                },
                onClick: () => setForm({ ...form, farbe: f }),
              }))))),
        h('div', { className: 'btn-row' },
          h('button', { className: 'btn primary', type: 'submit' }, edit ? 'Speichern' : 'Anlegen'),
          edit && h('button', { className: 'btn', type: 'button', onClick: () => setEdit(null) }, 'Abbrechen')),
      ),
    ),
  )
}

function RegelnPanel({ keywords, kategorien, refresh }) {
  const [form, setForm] = useState({ schluesselwort: '', kategorie_id: '' })
  return h('div', { className: 'grid grid-1-2' },
    h('div', { className: 'card' },
      h('div', { className: 'card-title' }, h('h2', null, 'Auto-Regeln'),
        h('span', { className: 'hint' }, `${keywords.length} Zuordnungen`)),
      h('p', { className: 'muted', style: { fontSize: 12.5, marginTop: -4, lineHeight: 1.6 } },
        'Neue CSV-Buchungen werden anhand dieser Schlüsselwörter automatisch kategorisiert. Beispiel: „rewe“ → Lebensmittel.'),
      h('div', { className: 'table-wrap' },
        h('table', null,
          h('thead', null, h('tr', null,
            h('th', null, 'Schlüsselwort'), h('th', null, 'Kategorie'), h('th', null, ''))),
          h('tbody', null, ...keywords.map((k) =>
            h('tr', { key: k.id },
              h('td', { className: 'strong' }, k.schluesselwort),
              h('td', null, `${k.icon} ${k.kategorie}`),
              h('td', null,
                h('button', {
                  className: 'btn sm danger',
                  onClick: () => refresh(() => api(`/keywords/${k.id}`, { method: 'DELETE' }), 'Regel gelöscht'),
                }, '🗑️')))))),
      ),
    ),
    h('div', { className: 'card' },
      h('div', { className: 'card-title' }, h('h2', null, 'Neue Regel')),
      h('form', {
        onSubmit: (e) => {
          e.preventDefault()
          refresh(() => api('/keywords', { method: 'POST', body: { schluesselwort: form.schluesselwort, kategorie_id: Number(form.kategorie_id) } }), 'Regel gespeichert')
          setForm({ schluesselwort: '', kategorie_id: '' })
        },
      },
        h('label', { className: 'field' }, h('span', null, 'Schlüsselwort *'),
          h('input', {
            className: 'input', value: form.schluesselwort, required: true,
            onChange: (e) => setForm({ ...form, schluesselwort: e.target.value }),
            placeholder: 'z. B. edeka',
          })),
        h('label', { className: 'field' }, h('span', null, 'Kategorie *'),
          h('select', {
            className: 'input', value: form.kategorie_id, required: true,
            onChange: (e) => setForm({ ...form, kategorie_id: e.target.value }),
          },
            h('option', { value: '' }, '– wählen –'),
            ...kategorien.map((k) => h('option', { key: k.id, value: k.id }, `${k.icon} ${k.name}`)))),
        h('button', { className: 'btn primary', type: 'submit' }, 'Regel speichern'),
      ),
      h('div', { style: { marginTop: 20 } },
        h('div', { className: 'card-title' }, h('h2', null, 'Batch-Zuordnung')),
        h('p', { className: 'faint', style: { lineHeight: 1.6 } },
          'Alle Buchungen, deren Beschreibung einen Begriff enthält, einer Kategorie zuweisen – z. B. Altbestände aufräumen.'),
        h(BatchZuordnung, { kategorien, refresh })),
    ),
  )
}

function BatchZuordnung({ kategorien, refresh }) {
  const [begriff, setBegriff] = useState('')
  const [kat, setKat] = useState('')
  const [info, setInfo] = useState(null)
  return h(React.Fragment, null,
    h('div', { className: 'grid grid-2' },
      h('label', { className: 'field' }, h('span', null, 'Suchbegriff'),
        h('input', { className: 'input', value: begriff, onChange: (e) => setBegriff(e.target.value), placeholder: 'muhle' })),
      h('label', { className: 'field' }, h('span', null, 'Ziel-Kategorie'),
        h('select', { className: 'input', value: kat, onChange: (e) => setKat(e.target.value) },
          h('option', { value: '' }, '– wählen –'),
          ...kategorien.map((k) => h('option', { key: k.id, value: k.id }, `${k.icon} ${k.name}`))))),
    h('button', {
      className: 'btn', disabled: !begriff || !kat,
      onClick: async () => {
        try {
          const r = await api('/buchungen/bulk-kategorie', { method: 'POST', body: { suchbegriff: begriff, kategorie_id: Number(kat) } })
          setInfo(`${r.aktualisiert} Buchungen aktualisiert`)
          notify(`Batch: ${r.aktualisiert} Buchungen`)
        } catch (e) { notify(e.message, 'err') }
      },
    }, 'Ausführen'),
    info && h('div', { className: 'faint', style: { marginTop: 8 } }, info),
  )
}

function SystemPanel({ system }) {
  const [log, setLog] = useState('')
  useEffect(() => { api('/log').then(setLog).catch(() => setLog('Kein Log vorhanden.')) }, [])
  if (!system) return h('div', { className: 'empty' }, 'Lade Systeminfos …')
  return h('div', { className: 'grid grid-2' },
    h('div', { className: 'card' },
      h('div', { className: 'card-title' }, h('h2', null, 'System')),
      h('div', { className: 'table-wrap' },
        h('table', null,
          h('tbody', null,
            ...[
              ['Version', system.version],
              ['Python', system.python],
              ['Host', system.hostname],
              ['Plattform', system.platform],
              ['Datenbank', system.db_groesse_kb + ' KB'],
            ].map(([k, v]) => h('tr', { key: k },
              h('td', { className: 'muted' }, k), h('td', { className: 'strong' }, String(v))))))),
      h('div', { style: { marginTop: 16 } },
        h('div', { className: 'btn-row' },
          h('button', { className: 'btn', onClick: () => api('/demo', { method: 'POST' }).then((r) => setLog(`${r.angelegt} Demo-Buchungen erzeugt`)) }, 'Demo-Daten laden'),
          h('a', { className: 'btn danger', href: '#' })),
      ),
      h('p', { className: 'faint', style: { lineHeight: 1.6, marginTop: 12 } },
        'Zum Zurücksetzen in der Shell:'),
      h('pre', { style: { background: 'rgba(3,7,18,0.6)', padding: '10px 12px', borderRadius: 10, fontSize: 11.5, overflow: 'auto' } },
        'rm -f /opt/haushaltsbuch/data/haushaltsbuch.db*'),
    ),
    h('div', { className: 'card' },
      h('div', { className: 'card-title' }, h('h2', null, 'Letzte Log-Zeilen'),
        h('span', { className: 'hint' }, '/var/log/haushaltsbuch.log')),
      h('pre', {
        style: {
          background: 'rgba(3,7,18,0.6)', padding: '12px 14px', borderRadius: 12,
          fontSize: 11, lineHeight: 1.7, overflow: 'auto', maxHeight: 340, margin: 0,
          color: '#9fb3d1', whiteSpace: 'pre-wrap',
        },
      }, log || '–'),
    ),
  )
}

ReactDOM.createRoot(document.getElementById('root')).render(h(App))

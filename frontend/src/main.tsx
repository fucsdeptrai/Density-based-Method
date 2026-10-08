import { StrictMode, useCallback, useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import L from 'leaflet'
import type { GeoJsonObject } from 'geojson'
import { CircleMarker, GeoJSON, MapContainer, Marker, TileLayer } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { DrawingControl } from './DrawingControl'
import { MapFocus } from './MapFocus'
import './style.css'

type Point = [number, number]
type Bootstrap = { areas: string[]; points: Point[] }
type Preview = {
  total_points: number
  available_matching_dates: number
  matching_dates: string[]
  points: Point[]
}
type Zone = {
  rank: number
  cluster_id: number
  pickup_count: number
  support_dates: number
  available_matching_dates: number
  pickups_per_matching_date: number
  marker_latitude: number
  marker_longitude: number
}
type Analysis = {
  n_points: number
  n_clusters: number
  noise_percentage: number
  largest_cluster_percentage: number
  matching_dates: string[]
  available_matching_dates: number
  zones: Zone[]
  map: { raw: Point[]; noise: Point[]; other: Point[]; ranked: { rank: number; cluster_id: number; points: Point[] }[] }
}
type StoredQuery = {
  selection: { borough?: string; geometry?: object }
  weekdays: string[]
  start_minute: number
  window_minutes: number
  eps_m: number
  min_samples: number
}
const ZONE_COLORS = ['#dc2626', '#15803d', '#2563eb', '#ea580c', '#7e22ce', '#0891b2', '#be185d', '#65a30d', '#b45309', '#0f766e']
const WEEKDAYS = [
  ['Monday', 'Thứ Hai'], ['Tuesday', 'Thứ Ba'], ['Wednesday', 'Thứ Tư'],
  ['Thursday', 'Thứ Năm'], ['Friday', 'Thứ Sáu'], ['Saturday', 'Thứ Bảy'],
  ['Sunday', 'Chủ Nhật'],
] as const

async function readJson<T>(response: Response, fallback: string): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(typeof body?.detail?.message === 'string' ? body.detail.message : fallback)
  }
  return response.json() as Promise<T>
}

function formatMinute(value: number): string {
  const minute = value % 1440
  return `${String(Math.floor(minute / 60)).padStart(2, '0')}:${String(minute % 60).padStart(2, '0')}`
}

function App() {
  const [bootstrap, setBootstrap] = useState<Bootstrap | null>(null)
  const [borough, setBorough] = useState('Brooklyn')
  const [spatialMode, setSpatialMode] = useState<'borough' | 'draw'>('borough')
  const [geometry, setGeometry] = useState<object | null>(null)
  const [clearRevision, setClearRevision] = useState(0)
  const [startTime, setStartTime] = useState('18:00')
  const [endTime, setEndTime] = useState('19:00')
  const [weekdays, setWeekdays] = useState<string[]>(['Friday'])
  const [maxDates, setMaxDates] = useState(5)
  const [epsM, setEpsM] = useState(70)
  const [minSamples, setMinSamples] = useState(15)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [analysisKey, setAnalysisKey] = useState('')
  const [topK, setTopK] = useState(3)
  const [analyzing, setAnalyzing] = useState(false)
  const [error, setError] = useState('')
  const onDrawChange = useCallback((nextGeometry: object | null) => setGeometry(nextGeometry), [])
  const minute = (value: string) => {
    const [hour, part] = value.split(':').map(Number)
    return hour * 60 + part
  }
  const startMinute = minute(startTime)
  const windowMinutes = (minute(endTime) - startMinute + 1440) % 1440 || 1440
  const contextQuery = {
    selection: spatialMode === 'borough' ? { borough } : { geometry },
    weekdays, max_matching_dates: maxDates,
    start_minute: startMinute, window_minutes: windowMinutes,
  }
  const analysisQuery = { ...contextQuery, eps_m: epsM, min_samples: minSamples }
  const contextKey = JSON.stringify(contextQuery)
  const currentAnalysisKey = JSON.stringify(analysisQuery)
  const analyzedQuery = useMemo(() => analysisKey ? JSON.parse(analysisKey) as StoredQuery : null, [analysisKey])
  const analyzedSelection = analyzedQuery?.selection

  useEffect(() => {
    fetch('/api/bootstrap')
      .then(response => readJson<Bootstrap>(response, 'Không tải được dữ liệu pickup.'))
      .then(data => {
        setBootstrap(data)
        setBorough(data.areas.includes('Brooklyn') ? 'Brooklyn' : data.areas[0] ?? '')
      })
      .catch(cause => setError(cause instanceof Error ? cause.message : String(cause)))
  }, [])

  useEffect(() => {
    if (!bootstrap || !weekdays.length || maxDates < 1 || maxDates > 30 || (spatialMode === 'borough' && !borough) || (spatialMode === 'draw' && !geometry)) {
      setPreview(null)
      return
    }
    const controller = new AbortController()
    setPreview(null)
    setError('')
    const timer = window.setTimeout(() => {
      fetch('/api/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: contextKey,
        signal: controller.signal,
      })
        .then(response => readJson<Preview>(response, 'Không xem trước được truy vấn.'))
        .then(setPreview)
        .catch(cause => {
          if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : String(cause))
        })
    }, 250)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [bootstrap, borough, contextKey, spatialMode, geometry, weekdays.length, maxDates])

  function analyze() {
    setAnalyzing(true)
    setError('')
    fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: currentAnalysisKey,
    })
      .then(response => readJson<Analysis>(response, 'Không phân tích được truy vấn.'))
      .then(result => {
        setAnalysis(result)
        setAnalysisKey(currentAnalysisKey)
      })
      .catch(cause => setError(cause instanceof Error ? cause.message : String(cause)))
      .finally(() => setAnalyzing(false))
  }

  return (
    <main>
      <h1>Vùng đón khách ưu tiên trong lịch sử</h1>
      <p className="intro">Tự chọn một khu vực và ngữ cảnh thời gian để kiểm tra hotspot pickup lịch sử. Kết quả không phải dữ liệu thời gian thực, dự báo nhu cầu hay đảm bảo có khách.</p>
      <div className="app-layout">
      <aside className="controls" aria-label="Bộ lọc">
      <h2>Ngữ cảnh phân tích</h2>
      <fieldset>
        <legend>Cách chọn khu vực</legend>
        <label><input type="radio" name="spatial-mode" checked={spatialMode === 'borough'} onChange={() => setSpatialMode('borough')} /> Theo borough</label>
        <label><input type="radio" name="spatial-mode" checked={spatialMode === 'draw'} onChange={() => setSpatialMode('draw')} /> Vẽ một vùng</label>
      </fieldset>
      {spatialMode === 'borough' ? <>
        <label htmlFor="borough">Borough</label>
        <select id="borough" value={borough} onChange={event => setBorough(event.target.value)}>
          {bootstrap?.areas.map(area => <option key={area}>{area}</option>)}
        </select>
      </> : <>
        <p>Vẽ một rectangle hoặc polygon trên bản đồ. Hình mới sẽ thay thế vùng trước.</p>
        {geometry && <button onClick={() => { setGeometry(null); setClearRevision(value => value + 1) }}>Xóa vùng đã vẽ</button>}
      </>}
      <fieldset>
        <legend>Ngày trong tuần</legend>
        {WEEKDAYS.map(([day, label]) => <label key={day}>
          <input type="checkbox" checked={weekdays.includes(day)} onChange={event =>
            setWeekdays(current => WEEKDAYS.map(([name]) => name).filter(name =>
              name === day ? event.target.checked : current.includes(name)))} /> {label}
        </label>)}
      </fieldset>
      {!weekdays.length && <p role="alert">Chọn ít nhất một ngày trong tuần.</p>}
      <label htmlFor="max-dates">Số ngày phù hợp gần nhất</label>
      <input id="max-dates" type="number" min="1" max="30" value={maxDates || ''} onChange={event => setMaxDates(Number(event.target.value))} />
      <label htmlFor="start-time">Bắt đầu</label>
      <input id="start-time" type="time" step="900" value={startTime} onChange={event => setStartTime(event.target.value)} />
      <label htmlFor="end-time">Kết thúc</label>
      <input id="end-time" type="time" step="900" value={endTime} onChange={event => setEndTime(event.target.value)} />
      <details>
        <summary>Cài đặt DBSCAN</summary>
        <label htmlFor="eps-m">eps (mét)</label>
        <input id="eps-m" type="number" min="20" max="200" step="5" value={epsM || ''} onChange={event => setEpsM(Number(event.target.value))} />
        <label htmlFor="min-samples">MinPts</label>
        <input id="min-samples" type="number" min="3" max="50" value={minSamples || ''} onChange={event => setMinSamples(Number(event.target.value))} />
      </details>
      <p className="help-text">Noise chỉ có nghĩa là chưa đủ mật độ theo truy vấn và tham số hiện tại. Ứng dụng không tự điều chỉnh tham số.</p>
      </aside>
      <article className="workspace">
      {error && <p role="alert" className="notice error">{error}</p>}
      <h2>Pickup thô theo ngữ cảnh đang chọn</h2>
      {preview && <>
        <p className="preview-count">Truy vấn hiện tại có {preview.total_points.toLocaleString('vi-VN')} pickup trên {preview.available_matching_dates} ngày phù hợp.</p>
        <p className="help-text">Ngày được dùng: {preview.matching_dates.map(value => new Date(`${value}T00:00:00`).toLocaleDateString('vi-VN')).join(', ')}</p>
        {preview.total_points > 200_000 && <p role="alert" className="notice warning">Vượt ngưỡng chạy tương tác 200.000 pickup. Hãy thu hẹp khu vực, ngày hoặc khung giờ.</p>}
        {preview.total_points === 0 && <p role="alert" className="notice warning">Không có pickup nào khớp truy vấn hiện tại.</p>}
      </>}
      <section aria-label="Bản đồ pickup" className="map-panel">
        <MapContainer center={[40.6782, -73.9442]} zoom={12} scrollWheelZoom className="map">
          <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
          <MapFocus borough={spatialMode === 'borough' ? borough : undefined} geometry={spatialMode === 'draw' ? geometry : null} />
          {spatialMode === 'draw' && <DrawingControl onChange={onDrawChange} clearRevision={clearRevision} geometry={geometry} />}
          {(preview?.points ?? bootstrap?.points ?? []).map(([lat, lon], index) =>
            <CircleMarker key={index} center={[lat, lon]} radius={2} pathOptions={{ pmIgnore: true, stroke: false, fillColor: '#4b5563', fillOpacity: 0.45 }} />)}
        </MapContainer>
      </section>
      <p className="help-text">Bản đồ chỉ lấy mẫu để hiển thị; số pickup được đếm trên toàn bộ truy vấn.</p>
      <button className="primary-button" disabled={!preview || !preview.total_points || preview.total_points > 200_000 || analyzing || epsM < 20 || epsM > 200 || minSamples < 3 || minSamples > 50} onClick={analyze}>{analyzing ? 'Đang phân tích…' : 'Tìm vùng ưu tiên'}</button>
      {analysis && analysisKey !== currentAnalysisKey && <p role="status" className="notice">Bộ lọc đã thay đổi. Kết quả bên dưới vẫn thuộc lần phân tích gần nhất.</p>}
      {analysis && <div className="result-layout">
      <section aria-label="Kết quả phân tích" className="result-panel">
        <h2>Kết quả phân tích</h2>
        {analyzedQuery && <p className="help-text">
          {analyzedQuery.selection.borough ?? 'Vùng tùy chọn'} · {analyzedQuery.weekdays.map(day => WEEKDAYS.find(([name]) => name === day)?.[1] ?? day).join(', ')} · {formatMinute(analyzedQuery.start_minute)}–{formatMinute(analyzedQuery.start_minute + analyzedQuery.window_minutes)}{analyzedQuery.start_minute + analyzedQuery.window_minutes > 1440 ? ' (+1 ngày)' : ''} · eps {analyzedQuery.eps_m}m · MinPts {analyzedQuery.min_samples}
        </p>}
        <p className="help-text">Ngày được phân tích: {analysis.matching_dates.map(value => new Date(`${value}T00:00:00`).toLocaleDateString('vi-VN')).join(', ')}</p>
        <p>Pickup đã lọc: {analysis.n_points.toLocaleString('vi-VN')}</p>
        <p>Hotspot tìm thấy: {analysis.n_clusters}</p>
        <p>Tỷ lệ noise: {analysis.noise_percentage.toFixed(1)}%</p>
        {analysis.largest_cluster_percentage > 50 && <p className="notice warning">Một cụm chứa hơn một nửa số pickup đã lọc. Đây có thể là dấu hiệu over-merging.</p>}
        <label htmlFor="top-k">Top K</label>
        <select id="top-k" value={topK} onChange={event => setTopK(Number(event.target.value))}>
          {Array.from({ length: 10 }, (_, index) => index + 1).map(value => <option key={value} value={value}>{value}</option>)}
        </select>
        <h2>Top {Math.min(topK, analysis.zones.length)} vùng ưu tiên</h2>
        {!analysis.zones.length && <p>Không có pickup nào đủ mật độ để tạo hotspot với cấu hình này.</p>}
        {analysis.zones.slice(0, topK).map(zone => <p key={zone.rank} className="zone-entry">Hotspot {zone.rank}: {zone.pickup_count} pickup lịch sử · xuất hiện trong {zone.support_dates}/{zone.available_matching_dates} ngày phù hợp · trung bình {zone.pickups_per_matching_date.toFixed(1)} pickup/ngày phù hợp</p>)}
      </section>
      <section aria-label="Bản đồ kết quả" className="map-panel result-map-panel">
        <MapContainer center={[40.6782, -73.9442]} zoom={12} scrollWheelZoom className="map result-map">
          <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
          <MapFocus borough={analyzedSelection?.borough} geometry={analyzedSelection?.geometry} />
          {analyzedSelection?.geometry && <GeoJSON data={analyzedSelection.geometry as GeoJsonObject} style={{ color: '#2563eb', weight: 3, fillOpacity: 0.08, dashArray: '7,5' }} />}
          {analysis.map.raw.map(([lat, lon], index) =>
            <CircleMarker key={index} center={[lat, lon]} radius={1.5} pathOptions={{ stroke: false, fillColor: '#4b5563', fillOpacity: 0.15 }} />)}
          {analysis.map.noise.map(([lat, lon], index) =>
            <CircleMarker key={`noise-${index}`} center={[lat, lon]} radius={2} pathOptions={{ stroke: false, fillColor: '#808080', fillOpacity: 0.55 }} />)}
          {analysis.map.other.map(([lat, lon], index) =>
            <CircleMarker key={`other-${index}`} center={[lat, lon]} radius={2} pathOptions={{ stroke: false, fillColor: '#64748b', fillOpacity: 0.3 }} />)}
          {analysis.map.ranked.flatMap(layer => layer.points.map(([lat, lon], index) =>
            <CircleMarker key={`ranked-${layer.rank}-${index}`} center={[lat, lon]} radius={2.5} pathOptions={{ stroke: false, fillColor: layer.rank <= topK ? ZONE_COLORS[layer.rank - 1] : '#64748b', fillOpacity: layer.rank <= topK ? 0.85 : 0.3 }} />))}
          {analysis.zones.slice(0, topK).map(zone => <Marker key={zone.rank}
            position={[zone.marker_latitude, zone.marker_longitude]}
            icon={L.divIcon({ className: 'hotspot-marker', html: String(zone.rank), iconSize: [28, 28] })} />)}
        </MapContainer>
        <p className="help-text">Chỉ các hotspot trong Top K được tô nổi. Marker nằm trong ô mật độ cao nhất; vùng vẽ là phạm vi lọc, không phải ranh giới DBSCAN.</p>
      </section>
      </div>}
      </article>
      </div>
    </main>
  )
}

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>)

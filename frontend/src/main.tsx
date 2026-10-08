import { StrictMode, useCallback, useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import L from 'leaflet'
import type { GeoJsonObject } from 'geojson'
import { CircleMarker, GeoJSON, MapContainer, Marker, TileLayer, ZoomControl } from 'react-leaflet'
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
    const messages: Record<string, string> = {
      DATA_UNAVAILABLE: 'Chưa tải được dữ liệu chuyến đi. Hãy thử lại sau.',
      INVALID_QUERY: 'Không thể xử lý bộ lọc. Hãy kiểm tra khu vực, ngày và giờ rồi thử lại.',
      QUERY_TOO_LARGE: 'Có quá nhiều lượt đón. Hãy thu hẹp khu vực, ngày hoặc khung giờ.',
    }
    throw new Error(messages[body?.detail?.code] ?? fallback)
  }
  return response.json() as Promise<T>
}

function errorMessage(cause: unknown): string {
  if (cause instanceof TypeError) return 'Không kết nối được với máy chủ. Hãy kiểm tra mạng và thử lại.'
  return cause instanceof Error ? cause.message : 'Đã xảy ra lỗi. Hãy thử lại.'
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
      .then(response => readJson<Bootstrap>(response, 'Chưa tải được dữ liệu chuyến đi. Hãy thử lại sau.'))
      .then(data => {
        setBootstrap(data)
        setBorough(data.areas.includes('Brooklyn') ? 'Brooklyn' : data.areas[0] ?? '')
      })
      .catch(cause => setError(errorMessage(cause)))
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
        .then(response => readJson<Preview>(response, 'Chưa tải được các điểm đón. Hãy thử lại.'))
        .then(setPreview)
        .catch(cause => {
          if (!controller.signal.aborted) setError(errorMessage(cause))
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
      .then(response => readJson<Analysis>(response, 'Chưa tìm được khu vực đón khách. Hãy thử lại.'))
      .then(result => {
        setAnalysis(result)
        setAnalysisKey(currentAnalysisKey)
      })
      .catch(cause => setError(errorMessage(cause)))
      .finally(() => setAnalyzing(false))
  }

  return (
    <main>
      <h1>Khám phá khu vực đón khách</h1>
      <p className="intro">Khám phá những khu vực ghi nhận nhiều lượt đón khách trong quá khứ theo ngày và khung giờ bạn lựa chọn. Dữ liệu mang tính tham khảo, không phản ánh nhu cầu theo thời gian thực.</p>
      <div className="app-layout">
      <aside className="controls" aria-label="Thiết lập tìm kiếm">
      <h2>Thiết lập tìm kiếm</h2>
      <fieldset>
        <legend>Phạm vi tìm kiếm</legend>
        <label><input type="radio" name="spatial-mode" checked={spatialMode === 'borough'} onChange={() => setSpatialMode('borough')} /> Theo khu vực hành chính</label>
        <label><input type="radio" name="spatial-mode" checked={spatialMode === 'draw'} onChange={() => setSpatialMode('draw')} /> Chọn khu vực trên bản đồ</label>
      </fieldset>
      {spatialMode === 'borough' ? <>
        <label htmlFor="borough">Khu vực hành chính</label>
        <select id="borough" value={borough} onChange={event => setBorough(event.target.value)}>
          {bootstrap?.areas.map(area => <option key={area}>{area}</option>)}
        </select>
      </> : <>
        <p>Vẽ một vùng trên bản đồ để xác định phạm vi tìm kiếm.</p>
        {geometry && <button onClick={() => { setGeometry(null); setClearRevision(value => value + 1) }}>Xóa khu vực đã chọn</button>}
      </>}
      <fieldset>
        <legend>Ngày hoạt động</legend>
        {WEEKDAYS.map(([day, label]) => <label key={day}>
          <input type="checkbox" checked={weekdays.includes(day)} onChange={event =>
            setWeekdays(current => WEEKDAYS.map(([name]) => name).filter(name =>
              name === day ? event.target.checked : current.includes(name)))} /> {label}
        </label>)}
      </fieldset>
      {!weekdays.length && <p role="alert">Chọn ít nhất một ngày hoạt động.</p>}
      <label htmlFor="max-dates">Số ngày gần nhất để thống kê</label>
      <input id="max-dates" type="number" min="1" max="30" value={maxDates || ''} onChange={event => setMaxDates(Number(event.target.value))} />
      <label htmlFor="start-time">Giờ bắt đầu</label>
      <input id="start-time" type="time" step="900" value={startTime} onChange={event => setStartTime(event.target.value)} />
      <label htmlFor="end-time">Giờ kết thúc</label>
      <input id="end-time" type="time" step="900" value={endTime} onChange={event => setEndTime(event.target.value)} />
      <details>
        <summary>Tùy chọn phân tích nâng cao</summary>
        <label htmlFor="eps-m">Bán kính gom điểm (m)</label>
        <input id="eps-m" type="number" min="20" max="200" step="5" value={epsM || ''} onChange={event => setEpsM(Number(event.target.value))} />
        <label htmlFor="min-samples">Số điểm đón tối thiểu trong bán kính</label>
        <input id="min-samples" type="number" min="3" max="50" value={minSamples || ''} onChange={event => setMinSamples(Number(event.target.value))} />
        <p className="help-text">Điểm đón thưa sẽ không được xếp vào khu vực nổi bật.</p>
      </details>
      </aside>
      <article className="workspace">
      {error && <p role="alert" className="notice error">{error}</p>}
      <h2>Bản đồ các điểm đón khách</h2>
      {!bootstrap && !error && <p role="status">Đang tải dữ liệu chuyến đi…</p>}
      {bootstrap && !preview && !error && weekdays.length > 0 && maxDates >= 1 && maxDates <= 30 && (spatialMode === 'borough' ? borough : geometry) && <p role="status">Đang tải các điểm đón…</p>}
      {preview && <>
        <p className="preview-count">{preview.total_points.toLocaleString('vi-VN')} lượt đón trong {preview.available_matching_dates} ngày phù hợp.</p>
        {preview.total_points > 200_000 && <p role="alert" className="notice warning">Có quá nhiều lượt đón để tìm khu vực. Hãy thu hẹp khu vực, ngày hoặc khung giờ.</p>}
        {preview.total_points === 0 && <p role="alert" className="notice warning">Không có lượt đón nào phù hợp. Hãy đổi khu vực, ngày hoặc giờ.</p>}
      </>}
      <section aria-label="Bản đồ các điểm đón khách" className="map-panel">
        <MapContainer center={[40.6782, -73.9442]} zoom={12} zoomControl={false} scrollWheelZoom className="map">
          <ZoomControl zoomInTitle="Phóng to" zoomOutTitle="Thu nhỏ" />
          <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
          <MapFocus borough={spatialMode === 'borough' ? borough : undefined} geometry={spatialMode === 'draw' ? geometry : null} />
          {spatialMode === 'draw' && <DrawingControl onChange={onDrawChange} clearRevision={clearRevision} geometry={geometry} />}
          {(preview?.points ?? bootstrap?.points ?? []).map(([lat, lon], index) =>
            <CircleMarker key={index} center={[lat, lon]} radius={2} pathOptions={{ pmIgnore: true, stroke: false, fillColor: '#4b5563', fillOpacity: 0.45 }} />)}
        </MapContainer>
      </section>
      <button className="primary-button" disabled={!preview || !preview.total_points || preview.total_points > 200_000 || analyzing || epsM < 20 || epsM > 200 || minSamples < 3 || minSamples > 50} onClick={analyze}>{analyzing ? 'Đang tìm khu vực…' : 'Tìm khu vực có nhiều lượt đón'}</button>
      {analysis && analysisKey !== currentAnalysisKey && <p role="status" className="notice">Bạn đã thay đổi bộ lọc. Nhấn nút tìm kiếm để cập nhật kết quả.</p>}
      {analysis && <div className="result-layout">
      <section aria-label="Khu vực đón khách nổi bật" className="result-panel">
        <h2>Khu vực đón khách nổi bật</h2>
        {analyzedQuery && <p className="help-text">
          {analyzedQuery.selection.borough ?? 'Khu vực đã chọn trên bản đồ'} · {analyzedQuery.weekdays.map(day => WEEKDAYS.find(([name]) => name === day)?.[1] ?? day).join(', ')} · {formatMinute(analyzedQuery.start_minute)}–{formatMinute(analyzedQuery.start_minute + analyzedQuery.window_minutes)}{analyzedQuery.start_minute + analyzedQuery.window_minutes > 1440 ? ' (+1 ngày)' : ''}
        </p>}
        <p>Tổng lượt đón phù hợp: {analysis.n_points.toLocaleString('vi-VN')}</p>
        <p>Số khu vực tìm thấy: {analysis.n_clusters}</p>
        <p>{analysis.noise_percentage.toLocaleString('vi-VN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}% lượt đón nằm ngoài các khu vực nổi bật.</p>
        {analysis.largest_cluster_percentage > 50 && <p className="notice warning">Một khu vực chiếm hơn một nửa số lượt đón. Các điểm đón có thể đã được gom quá rộng.</p>}
        <p className="help-text">Kết quả được tổng hợp từ các chuyến đi trong quá khứ. Khu vực có nhiều lượt đón không đồng nghĩa với việc hiện tại có khách đang chờ.</p>
        <label htmlFor="top-k">Số khu vực hiển thị</label>
        <select id="top-k" value={topK} onChange={event => setTopK(Number(event.target.value))}>
          {Array.from({ length: 10 }, (_, index) => index + 1).map(value => <option key={value} value={value}>{value}</option>)}
        </select>
        {analysis.zones.length > 0 && <h2>Đang hiển thị {Math.min(topK, analysis.zones.length)} khu vực</h2>}
        {!analysis.zones.length && <p>Chưa tìm thấy khu vực có đủ lượt đón. Hãy thử đổi bộ lọc hoặc tùy chọn phân tích nâng cao.</p>}
        {analysis.zones.slice(0, topK).map(zone => <p key={zone.rank} className="zone-entry">Khu vực {zone.rank}: {zone.pickup_count.toLocaleString('vi-VN')} lượt đón · trung bình {zone.pickups_per_matching_date.toLocaleString('vi-VN', { maximumFractionDigits: 1 })} lượt/ngày</p>)}
      </section>
      <section aria-label="Bản đồ kết quả" className="map-panel result-map-panel">
        <MapContainer center={[40.6782, -73.9442]} zoom={12} zoomControl={false} scrollWheelZoom className="map result-map">
          <ZoomControl zoomInTitle="Phóng to" zoomOutTitle="Thu nhỏ" />
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
        <p className="help-text">Các số trên bản đồ đánh dấu điểm có nhiều lượt đón trong từng khu vực nổi bật. Vùng bạn vẽ chỉ xác định phạm vi tìm kiếm.</p>
      </section>
      </div>}
      </article>
      </div>
    </main>
  )
}

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>)

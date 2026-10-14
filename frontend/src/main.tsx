import { StrictMode, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import L from 'leaflet'
import type { GeoJsonObject } from 'geojson'
import { CircleMarker, GeoJSON, MapContainer, Marker, ZoomControl } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { DrawingControl } from './DrawingControl'
import { MapFocus } from './MapFocus'
import { OfflineMapLayer } from './OfflineMapLayer'
import { ResultMapFocus } from './ResultMapFocus'
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
  const [previewKey, setPreviewKey] = useState('')
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [analysisKey, setAnalysisKey] = useState('')
  const [topK, setTopK] = useState(10)
  const [selectedClusterId, setSelectedClusterId] = useState<number | null>(null)
  const [mapView, setMapView] = useState<'preview' | 'result'>('preview')
  const [showMobileFilters, setShowMobileFilters] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const [error, setError] = useState('')
  const [offlineMapAvailable, setOfflineMapAvailable] = useState<boolean | null>(null)
  const [boundaries, setBoundaries] = useState<Record<string, GeoJsonObject>>({})
  const [showRawPoints, setShowRawPoints] = useState(false)
  const zoneListRef = useRef<HTMLDivElement>(null)
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
  const showResultMap = analysis !== null && mapView === 'result'
  const displayedZones = useMemo(() => analysis?.zones.slice(0, topK) ?? [], [analysis, topK])
  const displayedIds = useMemo(() => new Set(displayedZones.map(zone => zone.cluster_id)), [displayedZones])
  const displayedRanked = useMemo(() => analysis?.map.ranked.filter(layer => displayedIds.has(layer.cluster_id)) ?? [], [analysis, displayedIds])
  const invalidTime = !startTime || !endTime
  const validInputs = weekdays.length > 0 && maxDates >= 1 && maxDates <= 30 && epsM >= 20 && epsM <= 200 && minSamples >= 3 && minSamples <= 50 && !invalidTime && (spatialMode === 'borough' ? Boolean(borough) : Boolean(geometry))
  const previewReady = preview !== null && previewKey === contextKey
  const stale = analysis !== null && analysisKey !== currentAnalysisKey
  const selectedDays = weekdays.map(day => WEEKDAYS.find(([name]) => name === day)?.[1] ?? day).join(', ')
  const appliedDays = analyzedQuery?.weekdays.map(day => WEEKDAYS.find(([name]) => name === day)?.[1] ?? day).join(', ') ?? ''
  const selectedArea = spatialMode === 'borough' ? borough : 'Vùng đã chọn trên bản đồ'
  const boundary = (showResultMap ? analyzedSelection?.borough : spatialMode === 'borough' ? borough : undefined)

  useEffect(() => {
    if (selectedClusterId !== null && !displayedIds.has(selectedClusterId)) setSelectedClusterId(null)
  }, [displayedIds, selectedClusterId])

  useEffect(() => {
    if (selectedClusterId === null) return
    const list = zoneListRef.current
    const item = Array.from(list?.children ?? []).find(child => child.getAttribute('data-cluster-id') === String(selectedClusterId))
    if (!list || !item) return
    const listBounds = list.getBoundingClientRect()
    const itemBounds = item.getBoundingClientRect()
    if (itemBounds.top < listBounds.top) list.scrollTop += itemBounds.top - listBounds.top
    if (itemBounds.bottom > listBounds.bottom) list.scrollTop += itemBounds.bottom - listBounds.bottom
  }, [selectedClusterId])

  useEffect(() => {
    fetch('/maps/nyc.pmtiles', { headers: { Range: 'bytes=0-126' } })
      .then(response => setOfflineMapAvailable(response.status === 206))
      .catch(() => setOfflineMapAvailable(false))
  }, [])

  useEffect(() => {
    fetch('/boroughs.geojson')
      .then(response => response.ok ? response.json() : null)
      .then(data => {
        if (!data?.features) return
        setBoundaries(Object.fromEntries(data.features.map((feature: { properties: { BoroName: string } }) => [feature.properties.BoroName, feature])))
      })
      .catch(() => {})
  }, [])

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
    if (!bootstrap || !weekdays.length || maxDates < 1 || maxDates > 30 || invalidTime || (spatialMode === 'borough' && !borough) || (spatialMode === 'draw' && !geometry)) {
      setPreview(null)
      setPreviewKey('')
      return
    }
    const controller = new AbortController()
    setPreview(null)
    setPreviewKey('')
    setError('')
    const timer = window.setTimeout(() => {
      fetch('/api/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: contextKey,
        signal: controller.signal,
      })
        .then(response => readJson<Preview>(response, 'Chưa tải được các điểm đón. Hãy thử lại.'))
        .then(data => { setPreview(data); setPreviewKey(contextKey) })
        .catch(cause => {
          if (!controller.signal.aborted) setError(errorMessage(cause))
        })
    }, 250)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [bootstrap, borough, contextKey, spatialMode, geometry, weekdays.length, maxDates, invalidTime])

  function analyze() {
    if (analyzing || !validInputs || !previewReady || !preview.total_points || preview.total_points > 200_000) return
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
        setSelectedClusterId(null)
        setMapView('result')
      })
      .catch(cause => setError(errorMessage(cause)))
      .finally(() => setAnalyzing(false))
  }

  return (
    <main>
      <span className="data-tag">Dữ liệu lịch sử</span>
      <h1>Khám phá khu vực đón khách</h1>
      <p className="intro">Khám phá những khu vực ghi nhận nhiều lượt đón khách trong quá khứ theo ngày và khung giờ bạn lựa chọn. Dữ liệu mang tính tham khảo, không phản ánh nhu cầu theo thời gian thực.</p>
      <div className="app-layout">
      <aside className="controls" aria-label="Thiết lập tìm kiếm">
      <div className="controls-heading"><h2>Thiết lập tìm kiếm</h2><button className="text-button mobile-filter-toggle" aria-expanded={showMobileFilters} onClick={() => setShowMobileFilters(value => !value)}>{showMobileFilters ? 'Thu gọn' : 'Mở bộ lọc'}</button></div>
      <div className={`controls-body${showMobileFilters ? ' open' : ''}`}>
      <div className="filter-fields">
      <fieldset>
        <legend>Phạm vi</legend>
        <label><input type="radio" name="spatial-mode" checked={spatialMode === 'borough'} onChange={() => setSpatialMode('borough')} /> Theo khu vực hành chính</label>
        <label><input type="radio" name="spatial-mode" checked={spatialMode === 'draw'} onChange={() => { setSpatialMode('draw'); setMapView('preview') }} /> Chọn khu vực trên bản đồ</label>
      </fieldset>
      {spatialMode === 'borough' ? <>
        <label htmlFor="borough">Khu vực hành chính</label>
        <select id="borough" value={borough} onChange={event => setBorough(event.target.value)}>
          {bootstrap?.areas.map(area => <option key={area}>{area}</option>)}
        </select>
      </> : <>
        <p>Vẽ một vùng trên bản đồ để xác định phạm vi tìm kiếm.</p>
        {geometry && <button className="text-button" onClick={() => { setGeometry(null); setClearRevision(value => value + 1) }}>Xóa khu vực đã chọn</button>}
      </>}
      <fieldset className="weekday-fieldset">
        <legend>Ngày hoạt động</legend>
        <div className="weekday-grid">
        {WEEKDAYS.map(([day, label]) => <label key={day}>
          <input type="checkbox" checked={weekdays.includes(day)} onChange={event =>
            setWeekdays(current => WEEKDAYS.map(([name]) => name).filter(name =>
              name === day ? event.target.checked : current.includes(name)))} /> {label}
        </label>)}
        </div>
      </fieldset>
      {!weekdays.length && <p role="alert">Chọn ít nhất một ngày hoạt động.</p>}
      <label htmlFor="max-dates">Số ngày gần nhất để thống kê</label>
      <input id="max-dates" type="number" min="1" max="30" value={maxDates || ''} onChange={event => setMaxDates(Number(event.target.value))} />
      <p className="help-text">Lấy {maxDates || 0} ngày {selectedDays || 'đã chọn'} gần nhất có dữ liệu.</p>
      <div className="time-fields">
      <div>
      <label htmlFor="start-time">Giờ bắt đầu</label>
      <input id="start-time" type="time" step="900" value={startTime} onChange={event => setStartTime(event.target.value)} />
      </div><div>
      <label htmlFor="end-time">Giờ kết thúc</label>
      <input id="end-time" type="time" step="900" value={endTime} onChange={event => setEndTime(event.target.value)} />
      </div></div>
      {invalidTime && <p role="alert">Chọn giờ bắt đầu và giờ kết thúc.</p>}
      <details>
        <summary>Tùy chọn phân tích nâng cao</summary>
        <label htmlFor="eps-m" title="Khoảng cách tối đa giữa các điểm gần nhau khi tìm khu vực tập trung.">Bán kính gom điểm (m)</label>
        <input id="eps-m" type="number" min="20" max="200" step="5" value={epsM || ''} onChange={event => setEpsM(Number(event.target.value))} />
        <label htmlFor="min-samples" title="Một điểm cần có ít nhất số lượt đón này trong bán kính, tính cả chính nó, để bắt đầu tạo cụm.">Số điểm đón tối thiểu trong bán kính</label>
        <input id="min-samples" type="number" min="3" max="50" value={minSamples || ''} onChange={event => setMinSamples(Number(event.target.value))} />
        <p className="help-text">Điểm đón thưa sẽ không được xếp vào khu vực nổi bật.</p>
      </details>
      </div>
      <div className="filter-actions">
        <p className="filter-summary">{validInputs ? `${selectedArea} · ${selectedDays} · ${startTime}–${endTime} · ${maxDates} ngày gần nhất có dữ liệu` : 'Chọn khu vực, ngày và giờ để phân tích.'}</p>
        {stale && <span className="stale-badge">Bộ lọc đã thay đổi</span>}
        <button className="primary-button" disabled={!previewReady || !preview?.total_points || preview.total_points > 200_000 || analyzing || !validInputs} onClick={analyze}>
          {analyzing && <span className="spinner" aria-hidden="true" />}{analyzing ? 'Đang phân tích…' : 'Phân tích điểm nóng'}
        </button>
      </div>
      </div>
      </aside>
      <article className="workspace">
      {error && <p role="alert" className="notice error">{error}</p>}
      <h2>{showResultMap ? 'Bản đồ kết quả' : 'Bản đồ các điểm đón khách'}</h2>
      {offlineMapAvailable === false && <p role="status" className="notice warning">Chưa có nền bản đồ trên máy. Hãy chuẩn bị gói bản đồ offline rồi tải lại trang.</p>}
      {!bootstrap && !error && <p role="status">Đang tải dữ liệu chuyến đi…</p>}
      {bootstrap && !preview && !error && weekdays.length > 0 && maxDates >= 1 && maxDates <= 30 && !invalidTime && (spatialMode === 'borough' ? borough : geometry) && <p role="status">Đang tải các điểm đón…</p>}
      {preview && <>
        {(!analysis || stale) && <p className="preview-count">{preview.total_points.toLocaleString('vi-VN')} lượt đón phù hợp · {preview.available_matching_dates} ngày có dữ liệu</p>}
        {preview.total_points > 200_000 && <p role="alert" className="notice warning">Có quá nhiều lượt đón để tìm khu vực. Hãy thu hẹp khu vực, ngày hoặc khung giờ.</p>}
        {preview.total_points === 0 && <p role="alert" className="notice warning">Không có lượt đón nào phù hợp. Hãy đổi khu vực, ngày hoặc giờ.</p>}
      </>}
      {stale && <p role="status" className="notice">Bạn đã thay đổi bộ lọc. Nhấn Phân tích điểm nóng để cập nhật kết quả.</p>}
      {analysis && <div className={`result-overview${analyzing ? ' pending' : ''}`}>
        <div className="result-stats">
          <div><strong>{analysis.n_points.toLocaleString('vi-VN')}</strong><span>lượt đón phù hợp</span></div>
          <div><strong>{analysis.n_clusters.toLocaleString('vi-VN')}</strong><span>khu vực ứng viên</span></div>
          <div><strong>{analysis.available_matching_dates.toLocaleString('vi-VN')}</strong><span>ngày có dữ liệu</span></div>
        </div>
        {analyzedQuery && <div className="filter-chips" aria-label="Bộ lọc của kết quả">
          <span>{analyzedQuery.selection.borough ?? 'Vùng đã chọn trên bản đồ'}</span>
          <span>{appliedDays}</span>
          <span>{formatMinute(analyzedQuery.start_minute)}–{formatMinute(analyzedQuery.start_minute + analyzedQuery.window_minutes)}{analyzedQuery.start_minute + analyzedQuery.window_minutes > 1440 ? ' (+1 ngày)' : ''}</span>
          <span>{analysis.available_matching_dates} ngày có dữ liệu</span>
        </div>}
      </div>}
      {analysis && <div className="map-tabs" role="group" aria-label="Chế độ xem bản đồ">
        <button className={mapView === 'preview' ? 'active' : ''} aria-pressed={mapView === 'preview'} onClick={() => setMapView('preview')}>Hiện điểm dữ liệu</button>
        <button className={mapView === 'result' ? 'active' : ''} aria-pressed={mapView === 'result'} onClick={() => setMapView('result')}>Kết quả phân tích</button>
      </div>}
      <div className={analysis ? `result-layout${analyzing ? ' pending' : ''}` : undefined}>
      <section aria-label={showResultMap ? 'Bản đồ kết quả' : 'Bản đồ các điểm đón khách'} className={`map-panel${analysis ? ' result-map-panel' : ''}`}>
        <MapContainer center={[40.6782, -73.9442]} zoom={12} zoomControl={false} scrollWheelZoom className="map">
          <ZoomControl zoomInTitle="Phóng to" zoomOutTitle="Thu nhỏ" />
          {offlineMapAvailable && <OfflineMapLayer />}
          {showResultMap
            ? displayedZones.length > 0
              ? <ResultMapFocus zones={displayedZones} ranked={displayedRanked} selectedClusterId={selectedClusterId} analysisKey={analysisKey} geometry={analyzedSelection?.geometry} />
              : <MapFocus borough={analyzedSelection?.borough} geometry={analyzedSelection?.geometry} />
            : <MapFocus borough={spatialMode === 'borough' ? borough : undefined} geometry={spatialMode === 'draw' ? geometry : null} />}
          {!showResultMap && spatialMode === 'draw' && <DrawingControl onChange={onDrawChange} clearRevision={clearRevision} geometry={geometry} />}
          {boundary && boundaries[boundary] && <GeoJSON key={boundary} data={boundaries[boundary]} style={{ color: '#526173', weight: 2, fillOpacity: 0, interactive: false }} />}
          {!showResultMap && (preview?.points ?? bootstrap?.points ?? []).map(([lat, lon], index) =>
            <CircleMarker key={index} center={[lat, lon]} radius={2.5} pathOptions={{ pmIgnore: true, stroke: false, fillColor: '#374151', fillOpacity: 0.75 }} />)}
          {showResultMap && analyzedSelection?.geometry && <GeoJSON data={analyzedSelection.geometry as GeoJsonObject} style={{ color: '#2563eb', weight: 3, fillOpacity: 0.08, dashArray: '7,5' }} />}
          {showResultMap && showRawPoints && analysis.map.raw.map(([lat, lon], index) =>
            <CircleMarker key={`raw-${index}`} center={[lat, lon]} radius={2} pathOptions={{ stroke: false, fillColor: '#374151', fillOpacity: 0.25 }} />)}
          {showResultMap && showRawPoints && analysis.map.noise.map(([lat, lon], index) =>
            <CircleMarker key={`noise-${index}`} center={[lat, lon]} radius={2.5} pathOptions={{ stroke: false, fillColor: '#4b5563', fillOpacity: 0.45 }} />)}
          {showResultMap && showRawPoints && analysis.map.other.map(([lat, lon], index) =>
            <CircleMarker key={`other-${index}`} center={[lat, lon]} radius={2.5} pathOptions={{ stroke: false, fillColor: '#475569', fillOpacity: 0.35 }} />)}
          {showResultMap && analysis.map.ranked.flatMap(layer => layer.points.map(([lat, lon], index) =>
            <CircleMarker key={`ranked-${layer.cluster_id}-${index}`} center={[lat, lon]} radius={selectedClusterId === layer.cluster_id ? 5 : 3.5} pathOptions={{ stroke: false, fillColor: displayedIds.has(layer.cluster_id) ? ZONE_COLORS[(layer.rank - 1) % ZONE_COLORS.length] : '#64748b', fillOpacity: displayedIds.has(layer.cluster_id) ? selectedClusterId === null || selectedClusterId === layer.cluster_id ? 0.8 : 0.18 : 0.25 }} eventHandlers={{ click: () => { if (displayedIds.has(layer.cluster_id)) setSelectedClusterId(layer.cluster_id) }, mouseover: event => event.target.setStyle({ radius: 5 }), mouseout: event => event.target.setStyle({ radius: selectedClusterId === layer.cluster_id ? 5 : 3.5 }) }} />))}
          {showResultMap && displayedZones.map(zone => <Marker key={zone.cluster_id}
            position={[zone.marker_latitude, zone.marker_longitude]}
            title={`Khu vực ${zone.rank}`}
            zIndexOffset={selectedClusterId === zone.cluster_id ? 1000 : 500 - zone.rank}
            eventHandlers={{ click: () => setSelectedClusterId(current => current === zone.cluster_id ? null : zone.cluster_id) }}
            icon={L.divIcon({ className: `hotspot-marker${selectedClusterId === zone.cluster_id ? ' selected' : ''}`, html: `<span style="background:${ZONE_COLORS[(zone.rank - 1) % ZONE_COLORS.length]}">${zone.rank}</span>`, iconSize: [36, 36], iconAnchor: [18, 18] })} />)}
        </MapContainer>
        {showResultMap && analysis.n_clusters === 0 && <p className="map-empty" role="status">Chưa tìm thấy điểm nóng trong phạm vi này. Hãy thử khung giờ khác hoặc chỉnh tùy chọn nâng cao.</p>}
        {showResultMap && <div className="map-legend" aria-label="Chú giải bản đồ">
          <span><i className="legend-hotspot" /> Điểm nóng và thứ hạng</span>
          {(Boolean(analyzedSelection?.geometry) || Boolean(boundary && boundaries[boundary])) && <span><i className="legend-boundary" /> Ranh giới khu vực</span>}
          {showRawPoints && <span><i className="legend-noise" /> Điểm dữ liệu, gồm điểm nhiễu</span>}
          <label><input type="checkbox" checked={showRawPoints} onChange={event => setShowRawPoints(event.target.checked)} /> Hiện điểm dữ liệu</label>
        </div>}
      </section>
      {analysis && <>
      <section aria-label="Khu vực đón khách nổi bật" className="result-panel">
        <h2>{displayedZones.length ? `Top ${displayedZones.length} khu vực nổi bật` : 'Khu vực đón khách nổi bật'}</h2>
        {analysis.zones.length > 0 && <>
          <div className="result-toolbar">
            <label htmlFor="top-k">Hiển thị tối đa</label>
            <select id="top-k" aria-label="Số khu vực tối đa hiển thị" value={topK} onChange={event => setTopK(Number(event.target.value))}>
              {Array.from({ length: 10 }, (_, index) => index + 1).map(value => <option key={value} value={value}>{value}</option>)}
            </select>
            {selectedClusterId !== null && <button className="text-button" onClick={() => setSelectedClusterId(null)}>Xem tất cả</button>}
          </div>
          <div className="zone-list" ref={zoneListRef}>
            {displayedZones.map(zone => <button key={zone.cluster_id} data-cluster-id={zone.cluster_id} className={`zone-entry${selectedClusterId === zone.cluster_id ? ' selected' : ''}`} aria-pressed={selectedClusterId === zone.cluster_id} onClick={() => { setMapView('result'); setSelectedClusterId(current => current === zone.cluster_id ? null : zone.cluster_id) }}>
              <span className="zone-heading"><span className="zone-badge" style={{ backgroundColor: ZONE_COLORS[(zone.rank - 1) % ZONE_COLORS.length] }}>#{zone.rank}</span> Khu vực {zone.rank}</span>
              <span>{zone.pickup_count.toLocaleString('vi-VN')} lượt đón · {analysis.n_points ? (zone.pickup_count / analysis.n_points * 100).toLocaleString('vi-VN', { maximumFractionDigits: 1 }) : 0}% tổng lượt đón</span>
              <span className="zone-subtext">Trung bình {zone.pickups_per_matching_date.toLocaleString('vi-VN', { maximumFractionDigits: 1 })} lượt/ngày có dữ liệu</span>
            </button>)}
          </div>
        </>}
        {!analysis.zones.length && <p role="status">Có {analysis.n_points.toLocaleString('vi-VN')} lượt đón nhưng chưa tìm thấy điểm nóng đủ tập trung. Hãy thử khung giờ khác hoặc chỉnh tùy chọn nâng cao.</p>}
        <div className="result-footnote">
          <p>Hiển thị {displayedZones.length}/{analysis.n_clusters} khu vực ứng viên · {analysis.noise_percentage.toLocaleString('vi-VN', { maximumFractionDigits: 1 })}% lượt đón chưa thuộc khu vực nào.</p>
          {analysis.largest_cluster_percentage > 50 && <p>Một khu vực chiếm hơn một nửa lượt đón; kết quả có thể đã được gom quá rộng.</p>}
          <p>Dữ liệu lịch sử, không cho biết hiện tại có khách đang chờ.</p>
        </div>
      </section>
      </>}
      </div>
      </article>
      </div>
    </main>
  )
}

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>)

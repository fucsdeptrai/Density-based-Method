import { useEffect, useRef } from 'react'
import L from 'leaflet'
import { useMap } from 'react-leaflet'

type ZoneLocation = { cluster_id: number; marker_latitude: number; marker_longitude: number }
type RankedPoints = { cluster_id: number; points: [number, number][] }

export function ResultMapFocus({ zones, ranked, selectedClusterId, analysisKey, geometry }: {
  zones: ZoneLocation[]
  ranked: RankedPoints[]
  selectedClusterId: number | null
  analysisKey: string
  geometry?: object | null
}) {
  const map = useMap()
  const userMoved = useRef(false)
  const previousAnalysis = useRef('')
  const previousSelection = useRef<number | null>(null)

  useEffect(() => {
    const markMoved = () => { userMoved.current = true }
    const container = map.getContainer()
    container.addEventListener('pointerdown', markMoved)
    container.addEventListener('wheel', markMoved)
    return () => {
      container.removeEventListener('pointerdown', markMoved)
      container.removeEventListener('wheel', markMoved)
    }
  }, [map])

  useEffect(() => {
    map.invalidateSize()
    const newAnalysis = previousAnalysis.current !== analysisKey
    const newSelection = previousSelection.current !== selectedClusterId
    previousAnalysis.current = analysisKey
    previousSelection.current = selectedClusterId
    if (newAnalysis) userMoved.current = false

    if (selectedClusterId !== null && newSelection) {
      const zone = zones.find(item => item.cluster_id === selectedClusterId)
      if (!zone) return
      const points = ranked.find(item => item.cluster_id === selectedClusterId)?.points ?? []
      const bounds = L.latLngBounds(points.length ? points : [[zone.marker_latitude, zone.marker_longitude]])
      bounds.extend([zone.marker_latitude, zone.marker_longitude])
      map.fitBounds(bounds, { padding: [48, 48], maxZoom: 15 })
      return
    }

    if (geometry && (newAnalysis || newSelection)) {
      map.fitBounds(L.geoJSON(geometry as Parameters<typeof L.geoJSON>[0]).getBounds(), { padding: [36, 36], maxZoom: 14 })
      return
    }

    if (!zones.length || (!newAnalysis && !newSelection && userMoved.current)) return
    const bounds = L.latLngBounds(zones.map(zone => [zone.marker_latitude, zone.marker_longitude]))
    map.fitBounds(bounds, { padding: [56, 56], maxZoom: 14 })
  }, [analysisKey, geometry, map, ranked, selectedClusterId, zones])

  return null
}

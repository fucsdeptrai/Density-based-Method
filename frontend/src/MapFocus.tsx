import { useEffect } from 'react'
import L from 'leaflet'
import { useMap } from 'react-leaflet'

const AREA_VIEWS: Record<string, { center: [number, number]; zoom: number }> = {
  Bronx: { center: [40.8448, -73.8648], zoom: 12 },
  Brooklyn: { center: [40.6782, -73.9442], zoom: 12 },
  EWR: { center: [40.6895, -74.1745], zoom: 13 },
  Manhattan: { center: [40.7831, -73.9712], zoom: 12 },
  Queens: { center: [40.7282, -73.7949], zoom: 11 },
  'Staten Island': { center: [40.5795, -74.1502], zoom: 11 },
}

export function MapFocus({ borough, geometry }: { borough?: string; geometry?: object | null }) {
  const map = useMap()
  useEffect(() => {
    if (geometry) {
      map.fitBounds(L.geoJSON(geometry as Parameters<typeof L.geoJSON>[0]).getBounds(), { padding: [20, 20] })
    } else {
      const view = AREA_VIEWS[borough ?? ''] ?? { center: [40.7128, -74.0060] as [number, number], zoom: 11 }
      map.setView(view.center, view.zoom)
    }
  }, [borough, geometry, map])
  return null
}

import { useEffect, useRef } from 'react'
import L from 'leaflet'
import { useMap } from 'react-leaflet'
import '@geoman-io/leaflet-geoman-free'
import '@geoman-io/leaflet-geoman-free/dist/leaflet-geoman.css'

type Props = {
  onChange: (geometry: object | null) => void
  clearRevision: number
  geometry: object | null
}

export function DrawingControl({ onChange, clearRevision, geometry }: Props) {
  const map = useMap()
  const drawn = useRef<L.Polygon | null>(null)
  const initialGeometry = useRef(geometry)
  const previousClearRevision = useRef(clearRevision)

  useEffect(() => {
    map.pm.setLang('en', {
      tooltips: {
        firstVertex: 'Nhấn để bắt đầu vẽ vùng',
        continueLine: 'Nhấn để thêm góc của vùng',
        finishPoly: 'Nhấn vào điểm đầu để hoàn tất vùng',
        finishRect: 'Nhấn để hoàn tất vùng',
      },
      actions: {
        finish: 'Hoàn tất',
        cancel: 'Hủy',
        removeLastVertex: 'Xóa góc vừa thêm',
      },
      buttonTitles: {
        drawPolyButton: 'Vẽ vùng nhiều cạnh',
        drawRectButton: 'Vẽ vùng chữ nhật',
        editButton: 'Chỉnh sửa vùng đã vẽ',
        dragButton: 'Di chuyển vùng đã vẽ',
        deleteButton: 'Xóa vùng đã vẽ',
      },
    })
    map.pm.addControls({
      drawMarker: false, drawCircleMarker: false, drawCircle: false,
      drawPolyline: false, drawText: false, cutPolygon: false,
      rotateMode: false, dragMode: false,
      drawPolygon: true, drawRectangle: true,
    })
    const update = () => onChange(drawn.current?.toGeoJSON().geometry ?? null)
    if (initialGeometry.current) {
      const restored = L.geoJSON(initialGeometry.current as Parameters<typeof L.geoJSON>[0])
      drawn.current = restored.getLayers()[0] as L.Polygon
      drawn.current.addTo(map)
      drawn.current.on('pm:edit', update)
    }
    const created = (event: { layer: L.Layer }) => {
      if (drawn.current) map.removeLayer(drawn.current)
      drawn.current = event.layer as L.Polygon
      drawn.current.on('pm:edit', update)
      update()
    }
    const removed = (event: { layer: L.Layer }) => {
      if (event.layer === drawn.current) {
        drawn.current = null
        onChange(null)
      }
    }
    map.on('pm:create', created)
    map.on('pm:remove', removed)
    return () => {
      map.off('pm:create', created)
      map.off('pm:remove', removed)
      map.pm.removeControls()
      if (drawn.current) map.removeLayer(drawn.current)
    }
  }, [map, onChange])

  useEffect(() => {
    if (previousClearRevision.current === clearRevision) return
    previousClearRevision.current = clearRevision
    if (drawn.current) {
      map.removeLayer(drawn.current)
      drawn.current = null
    }
  }, [clearRevision, map])

  return null
}

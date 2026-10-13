import { useEffect } from 'react'
import { useMap } from 'react-leaflet'
import { leafletLayer } from 'protomaps-leaflet'

export function OfflineMapLayer() {
  const map = useMap()

  useEffect(() => {
    const layer = leafletLayer({
      url: '/maps/nyc.pmtiles',
      flavor: 'light',
      lang: 'en',
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    })
    layer.addTo(map)
    return () => { layer.remove() }
  }, [map])

  return null
}

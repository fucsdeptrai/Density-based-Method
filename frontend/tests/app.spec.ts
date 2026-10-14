import { test, expect } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.route('**/maps/nyc.pmtiles', route => route.fulfill({ status: 404 }))
})

test('user sees the default context and its pickup preview', async ({ page }) => {
  await page.route('**/api/bootstrap', route => route.fulfill({ json: {
    areas: ['Brooklyn', 'Manhattan'],
    points: [[40.68, -73.94]],
  } }))
  await page.route('**/api/preview', route => route.fulfill({ json: {
    total_points: 12,
    available_matching_dates: 2,
    matching_dates: ['2024-01-05', '2024-01-12'],
    points: [[40.68, -73.94]],
  } }))

  await page.goto('/')

  await expect(page.getByRole('heading', { name: 'Khám phá khu vực đón khách' })).toBeVisible()
  await expect(page.getByText('Chưa có nền bản đồ trên máy.', { exact: false })).toBeVisible()
  await expect(page.getByLabel('Khu vực hành chính', { exact: true })).toHaveValue('Brooklyn')
  await expect(page.getByText('12 lượt đón', { exact: false })).toBeVisible()
})

test('user analyzes the context and sees ranked historical zones', async ({ page }) => {
  await page.route('**/api/bootstrap', route => route.fulfill({ json: {
    areas: ['Brooklyn'], points: [[40.68, -73.94]],
  } }))
  await page.route('**/api/preview', route => route.fulfill({ json: {
    total_points: 12, available_matching_dates: 2,
    matching_dates: ['2024-01-05', '2024-01-12'], points: [[40.68, -73.94]],
  } }))
  await page.route('**/api/analyze', route => route.fulfill({ json: {
    n_points: 12, n_clusters: 1, noise_percentage: 25,
    largest_cluster_percentage: 75,
    matching_dates: ['2024-01-05', '2024-01-12'], available_matching_dates: 2,
    zones: [{ rank: 1, cluster_id: 0, pickup_count: 9, support_dates: 2,
      available_matching_dates: 2, pickups_per_matching_date: 4.5,
      marker_latitude: 40.68, marker_longitude: -73.94 }],
    map: { raw: [], noise: [], other: [], ranked: [{ rank: 1, cluster_id: 0, points: [] }] },
  } }))

  await page.goto('/')
  await page.getByRole('button', { name: 'Phân tích điểm nóng' }).click()

  await expect(page.getByRole('heading', { name: 'Top 1 khu vực nổi bật' })).toBeVisible()
  await expect(page.locator('.result-stats')).toContainText('12')
  await expect(page.locator('.result-stats')).toContainText('1')
  await expect(page.getByLabel('Bộ lọc của kết quả')).toContainText('Thứ Sáu')
  await expect(page.locator('.map-legend')).toContainText('Điểm nóng và thứ hạng')
  await expect(page.getByRole('checkbox', { name: 'Hiện điểm dữ liệu' })).not.toBeChecked()
  await expect(page.getByRole('button', { name: /Khu vực 1.*9 lượt đón/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /Khu vực 1.*9 lượt đón/ })).toContainText('75% tổng lượt đón')
  await expect(page.locator('.result-footnote')).toContainText('25% lượt đón chưa thuộc khu vực nào')
})

test('user can change Top K after analysis without the API', async ({ page }) => {
  await page.route('**/api/bootstrap', route => route.fulfill({ json: {
    areas: ['Brooklyn'], points: [],
  } }))
  await page.route('**/api/preview', route => route.fulfill({ json: {
    total_points: 12, available_matching_dates: 1,
    matching_dates: ['2024-01-05'], points: [],
  } }))
  await page.route('**/api/analyze', route => route.fulfill({ json: {
    n_points: 12, n_clusters: 106, noise_percentage: 0,
    largest_cluster_percentage: 25,
    matching_dates: ['2024-01-05'], available_matching_dates: 1,
    zones: Array.from({ length: 10 }, (_, index) => index + 1).map(rank => ({ rank, cluster_id: rank * 7,
      pickup_count: 3, support_dates: 1, available_matching_dates: 1,
      pickups_per_matching_date: 3, marker_latitude: 40.68 + rank * 0.01,
      marker_longitude: -73.94 })),
    map: { raw: [], noise: [], other: [], ranked: [] },
  } }))

  await page.goto('/')
  await page.getByRole('button', { name: 'Phân tích điểm nóng' }).click()
  await expect(page.locator('.result-stats > div').nth(1)).toContainText('106')
  await expect(page.locator('.result-stats > div').nth(1)).toContainText('khu vực ứng viên')
  await expect(page.getByRole('heading', { name: 'Top 10 khu vực nổi bật' })).toBeVisible()
  await expect(page.locator('.result-footnote')).toContainText('Hiển thị 10/106 khu vực ứng viên')
  await expect(page.locator('.hotspot-marker')).toHaveCount(10)
  const listBox = await page.locator('.zone-list').boundingBox()
  const footnoteBox = await page.locator('.result-footnote').boundingBox()
  expect(listBox && footnoteBox && listBox.y < footnoteBox.y).toBeTruthy()
  await page.getByRole('region', { name: 'Bản đồ kết quả' }).scrollIntoViewIfNeeded()
  for (const marker of await page.locator('.hotspot-marker').all()) {
    await expect(marker).toBeInViewport()
  }

  await page.route('**/api/**', route => route.abort())
  await page.getByLabel('Số khu vực tối đa hiển thị').selectOption('3')
  await expect(page.locator('.result-footnote')).toContainText('Hiển thị 3/106 khu vực ứng viên')
  await expect(page.getByRole('button', { name: /Khu vực 4/ })).toHaveCount(0)
  await expect(page.locator('.hotspot-marker')).toHaveCount(3)
  await page.getByLabel('Số khu vực tối đa hiển thị').selectOption('4')

  await expect(page.locator('.result-footnote')).toContainText('Hiển thị 4/106 khu vực ứng viên')
  await expect(page.getByRole('button', { name: /Khu vực 4/ })).toBeVisible()
  await expect(page.locator('.hotspot-marker')).toHaveCount(4)

  await page.getByRole('button', { name: /Khu vực 4/ }).click()
  await expect(page.getByRole('button', { name: /Khu vực 4/ })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.locator('.hotspot-marker.selected')).toHaveCount(1)
  await page.getByLabel('Số khu vực tối đa hiển thị').selectOption('3')
  await expect(page.locator('.hotspot-marker.selected')).toHaveCount(0)
  await page.locator('.hotspot-marker[title="Khu vực 1"]').click()
  await expect(page.getByRole('button', { name: /Khu vực 1/ })).toHaveAttribute('aria-pressed', 'true')
  await page.getByRole('button', { name: 'Xem tất cả' }).click()
  await expect(page.locator('.hotspot-marker.selected')).toHaveCount(0)
})

test('changing the time updates preview and marks the previous analysis as old', async ({ page }) => {
  await page.route('**/api/bootstrap', route => route.fulfill({ json: {
    areas: ['Brooklyn'], points: [],
  } }))
  await page.route('**/api/preview', route => {
    const query = route.request().postDataJSON()
    return route.fulfill({ json: {
      total_points: query.start_minute === 1140 ? 7 : 12,
      available_matching_dates: 1, matching_dates: ['2024-01-05'], points: [],
    } })
  })
  await page.route('**/api/analyze', route => route.fulfill({ json: {
    n_points: 12, n_clusters: 0, noise_percentage: 100,
    largest_cluster_percentage: 0, matching_dates: ['2024-01-05'],
    available_matching_dates: 1, zones: [],
    map: { raw: [], noise: [], other: [], ranked: [] },
  } }))

  await page.goto('/')
  await page.getByRole('button', { name: 'Phân tích điểm nóng' }).click()
  await expect(page.getByText('Có 12 lượt đón nhưng chưa tìm thấy điểm nóng đủ tập trung.', { exact: false })).toBeVisible()
  await expect(page.locator('.map-empty')).toBeVisible()
  await expect(page.locator('.result-footnote')).toContainText('Hiển thị 0/0 khu vực ứng viên')
  await page.getByLabel('Giờ bắt đầu').fill('19:00')

  await expect(page.getByText('7 lượt đón', { exact: false })).toBeVisible()
  await expect(page.getByText('Bạn đã thay đổi bộ lọc. Nhấn Phân tích điểm nóng để cập nhật kết quả.')).toBeVisible()
  await expect(page.getByLabel('Bộ lọc của kết quả')).toContainText('Brooklyn')
  await expect(page.getByLabel('Bộ lọc của kết quả')).toContainText('18:00–19:00')
})

test('preview places pickup samples on an interactive map', async ({ page }) => {
  await page.route('**/api/bootstrap', route => route.fulfill({ json: {
    areas: ['Brooklyn'], points: [[40.68, -73.94]],
  } }))
  await page.route('**/api/preview', route => route.fulfill({ json: {
    total_points: 1, available_matching_dates: 1,
    matching_dates: ['2024-01-05'], points: [[40.68, -73.94]],
  } }))
  await page.goto('/')

  const map = page.getByRole('region', { name: 'Bản đồ các điểm đón khách' })
  await expect(map.locator('.leaflet-container')).toBeVisible()
  await expect(map.locator('path.leaflet-interactive')).toHaveCount(1)
})

test('drawing a rectangle previews the selected region', async ({ page }) => {
  await page.route('**/api/bootstrap', route => route.fulfill({ json: {
    areas: ['Brooklyn'], points: [],
  } }))
  await page.route('**/api/preview', route => {
    const query = route.request().postDataJSON()
    return route.fulfill({ json: {
      total_points: query.selection.geometry ? 7 : 12,
      available_matching_dates: 1, matching_dates: ['2024-01-05'], points: [],
    } })
  })
  await page.route('**/api/analyze', route => route.fulfill({ json: {
    n_points: 7, n_clusters: 0, noise_percentage: 100,
    largest_cluster_percentage: 0, matching_dates: ['2024-01-05'],
    available_matching_dates: 1, zones: [],
    map: { raw: [], noise: [], other: [], ranked: [] },
  } }))
  await page.goto('/')
  await page.getByRole('radio', { name: 'Chọn khu vực trên bản đồ' }).check()
  await expect(page.getByTitle('Vẽ vùng chữ nhật')).toBeVisible()
  await expect(page.getByTitle('Vẽ vùng nhiều cạnh')).toBeVisible()
  await expect(page.getByTitle('Phóng to')).toBeVisible()
  await page.locator('.leaflet-pm-icon-rectangle').click()
  const box = await page.locator('.leaflet-container').boundingBox()
  if (!box) throw new Error('Map did not render')
  await page.mouse.click(box.x + box.width * 0.4, box.y + box.height * 0.4)
  await page.mouse.move(box.x + box.width * 0.6, box.y + box.height * 0.6)
  await page.mouse.click(box.x + box.width * 0.6, box.y + box.height * 0.6)

  await expect(page.getByText('7 lượt đón', { exact: false })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Xóa khu vực đã chọn' })).toBeVisible()
  await page.getByRole('radio', { name: 'Theo khu vực hành chính' }).check()
  await page.getByRole('radio', { name: 'Chọn khu vực trên bản đồ' }).check()
  await expect(page.getByText('7 lượt đón', { exact: false })).toBeVisible()
  await expect(page.locator('.leaflet-container path.leaflet-interactive')).toHaveCount(1)
  await page.getByRole('button', { name: 'Phân tích điểm nóng' }).click()
  await expect(page.getByRole('region', { name: 'Bản đồ kết quả' })).toBeVisible()
  await expect(page.locator('.leaflet-container')).toHaveCount(1)
  await page.getByRole('button', { name: 'Hiện điểm dữ liệu' }).click()
  await expect(page.locator('.leaflet-container path.leaflet-interactive')).toHaveCount(1)
  await page.getByRole('button', { name: 'Xóa khu vực đã chọn' }).click()
  await expect(page.getByRole('button', { name: 'Phân tích điểm nóng' })).toBeDisabled()
  await expect(page.locator('.leaflet-container path.leaflet-interactive')).toHaveCount(0)
})

test('user can add a weekday to the recurring context', async ({ page }) => {
  await page.route('**/api/bootstrap', route => route.fulfill({ json: {
    areas: ['Brooklyn'], points: [],
  } }))
  await page.route('**/api/preview', route => {
    const query = route.request().postDataJSON()
    return route.fulfill({ json: {
      total_points: query.weekdays.includes('Monday') ? 20 : 12,
      available_matching_dates: 2,
      matching_dates: ['2024-01-05', '2024-01-08'], points: [],
    } })
  })

  await page.goto('/')
  await page.getByRole('checkbox', { name: 'Thứ Hai' }).check()

  await expect(page.getByText('20 lượt đón', { exact: false })).toBeVisible()
})

test('user can choose how many recent matching dates to pool', async ({ page }) => {
  await page.route('**/api/bootstrap', route => route.fulfill({ json: {
    areas: ['Brooklyn'], points: [],
  } }))
  await page.route('**/api/preview', route => {
    const query = route.request().postDataJSON()
    return route.fulfill({ json: {
      total_points: query.max_matching_dates === 2 ? 8 : 12,
      available_matching_dates: query.max_matching_dates,
      matching_dates: ['2024-01-05', '2024-01-12'], points: [],
    } })
  })

  await page.goto('/')
  await page.getByLabel('Số ngày gần nhất để thống kê').fill('2')

  await expect(page.getByText('8 lượt đón', { exact: false })).toBeVisible()
})

test('user can set DBSCAN distance and minimum support before analysis', async ({ page }) => {
  await page.route('**/api/bootstrap', route => route.fulfill({ json: {
    areas: ['Brooklyn'], points: [],
  } }))
  await page.route('**/api/preview', route => route.fulfill({ json: {
    total_points: 12, available_matching_dates: 1,
    matching_dates: ['2024-01-05'], points: [],
  } }))
  await page.route('**/api/analyze', route => {
    const query = route.request().postDataJSON()
    return route.fulfill({ json: {
      n_points: 12, n_clusters: query.eps_m === 100 && query.min_samples === 10 ? 2 : 1,
      noise_percentage: 0, largest_cluster_percentage: 50,
      matching_dates: ['2024-01-05'], available_matching_dates: 1,
      zones: [], map: { raw: [], noise: [], other: [], ranked: [] },
    } })
  })

  await page.goto('/')
  await page.getByText('Tùy chọn phân tích nâng cao').click()
  await page.getByLabel('Bán kính gom điểm (m)').fill('100')
  await page.getByLabel('Số điểm đón tối thiểu trong bán kính').fill('10')
  await page.getByRole('button', { name: 'Phân tích điểm nóng' }).click()

  await expect(page.locator('.result-stats')).toContainText('2')
  await expect(page.locator('.result-stats')).toContainText('khu vực ứng viên')
})

test('large preview asks the user to narrow the query', async ({ page }) => {
  await page.route('**/api/bootstrap', route => route.fulfill({ json: {
    areas: ['Brooklyn'], points: [],
  } }))
  await page.route('**/api/preview', route => route.fulfill({ json: {
    total_points: 200001, available_matching_dates: 5,
    matching_dates: ['2024-01-05'], points: [],
  } }))

  await page.goto('/')

  await expect(page.getByText('Có quá nhiều lượt đón để tìm khu vực. Hãy thu hẹp khu vực, ngày hoặc khung giờ.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Phân tích điểm nóng' })).toBeDisabled()
})

test('analysis error is explained to the user', async ({ page }) => {
  await page.route('**/api/bootstrap', route => route.fulfill({ json: {
    areas: ['Brooklyn'], points: [],
  } }))
  await page.route('**/api/preview', route => route.fulfill({ json: {
    total_points: 12, available_matching_dates: 1,
    matching_dates: ['2024-01-05'], points: [],
  } }))
  await page.route('**/api/analyze', route => route.fulfill({ status: 400, json: {
    detail: { code: 'INVALID_QUERY', message: 'Không có pickup nào khớp truy vấn hiện tại.' },
  } }))

  await page.goto('/')
  await page.getByRole('button', { name: 'Phân tích điểm nóng' }).click()

  await expect(page.getByRole('alert')).toContainText('Không thể xử lý bộ lọc. Hãy kiểm tra khu vực, ngày và giờ rồi thử lại.')
})

test('network error is explained in Vietnamese', async ({ page }) => {
  await page.route('**/api/bootstrap', route => route.abort())

  await page.goto('/')

  await expect(page.getByRole('alert')).toContainText('Không kết nối được với máy chủ. Hãy kiểm tra mạng và thử lại.')
})

test('new preview remains available after analysis without two large maps', async ({ page }) => {
  await page.route('**/api/bootstrap', route => route.fulfill({ json: {
    areas: ['Brooklyn'], points: [],
  } }))
  await page.route('**/api/preview', route => {
    const query = route.request().postDataJSON()
    return route.fulfill({ json: {
      total_points: query.start_minute === 1140 ? 7 : 12,
      available_matching_dates: 1, matching_dates: ['2024-01-05'],
      points: [[40.68, -73.94]],
    } })
  })
  await page.route('**/api/analyze', route => route.fulfill({ json: {
    n_points: 12, n_clusters: 0, noise_percentage: 100,
    largest_cluster_percentage: 0, matching_dates: ['2024-01-05'],
    available_matching_dates: 1, zones: [],
    map: { raw: [[40.75, -73.98]], noise: [], other: [], ranked: [] },
  } }))

  await page.goto('/')
  await page.getByRole('button', { name: 'Phân tích điểm nóng' }).click()
  await page.getByLabel('Giờ bắt đầu').fill('19:00')

  await expect(page.getByText('7 lượt đón', { exact: false })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Bản đồ các điểm đón khách' })).toHaveCount(0)
  await expect(page.locator('.leaflet-container')).toHaveCount(1)
  await page.getByRole('button', { name: 'Hiện điểm dữ liệu' }).click()
  await expect(page.getByRole('region', { name: 'Bản đồ các điểm đón khách' }).locator('path.leaflet-interactive')).toHaveCount(1)
  await expect(page.getByRole('region', { name: 'Bản đồ kết quả' })).toHaveCount(0)
  await expect(page.locator('.leaflet-container')).toHaveCount(1)
  await page.getByRole('button', { name: 'Kết quả phân tích' }).click()
  await expect(page.getByRole('region', { name: 'Bản đồ kết quả' }).locator('path.leaflet-interactive')).toHaveCount(0)
  await page.getByRole('checkbox', { name: 'Hiện điểm dữ liệu' }).check()
  await expect(page.getByRole('region', { name: 'Bản đồ kết quả' }).locator('path.leaflet-interactive')).toHaveCount(1)
  await expect(page.locator('.leaflet-container')).toHaveCount(1)
})

test('map moves to the selected area', async ({ page }) => {
  await page.route('**/api/bootstrap', route => route.fulfill({ json: {
    areas: ['Brooklyn', 'EWR'], points: [],
  } }))
  await page.route('**/api/preview', route => {
    const query = route.request().postDataJSON()
    return route.fulfill({ json: {
      total_points: 1, available_matching_dates: 1,
      matching_dates: ['2024-01-05'],
      points: [query.selection.borough === 'EWR' ? [40.6895, -74.1745] : [40.6782, -73.9442]],
    } })
  })
  await page.goto('/')
  await page.getByLabel('Khu vực hành chính', { exact: true }).selectOption('EWR')

  const map = page.getByRole('region', { name: 'Bản đồ các điểm đón khách' })
  await map.scrollIntoViewIfNeeded()
  await expect(map.locator('path.leaflet-interactive')).toBeInViewport()
})

test('filters can be expanded on a narrow screen', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.route('**/api/bootstrap', route => route.fulfill({ json: {
    areas: ['Brooklyn'], points: [],
  } }))
  await page.route('**/api/preview', route => route.fulfill({ json: {
    total_points: 12, available_matching_dates: 1,
    matching_dates: ['2024-01-05'], points: [],
  } }))

  await page.goto('/')
  await expect(page.getByLabel('Khu vực hành chính', { exact: true })).toBeHidden()
  await page.getByRole('button', { name: 'Mở bộ lọc' }).click()
  await expect(page.getByLabel('Khu vực hành chính', { exact: true })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Bản đồ các điểm đón khách' }).locator('.leaflet-container')).toBeVisible()
})

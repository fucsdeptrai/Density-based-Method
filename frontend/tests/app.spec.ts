import { test, expect } from '@playwright/test'

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
  await page.getByRole('button', { name: 'Tìm khu vực có nhiều lượt đón' }).click()

  await expect(page.getByRole('heading', { name: 'Khu vực đón khách nổi bật' })).toBeVisible()
  await expect(page.getByText('Khu vực 1: 9 lượt đón', { exact: false })).toBeVisible()
  await expect(page.getByText('25,0% lượt đón', { exact: false })).toBeVisible()
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
    n_points: 12, n_clusters: 4, noise_percentage: 0,
    largest_cluster_percentage: 25,
    matching_dates: ['2024-01-05'], available_matching_dates: 1,
    zones: [1, 2, 3, 4].map(rank => ({ rank, cluster_id: rank - 1,
      pickup_count: 3, support_dates: 1, available_matching_dates: 1,
      pickups_per_matching_date: 3, marker_latitude: 40.68 + rank * 0.01,
      marker_longitude: -73.94 })),
    map: { raw: [], noise: [], other: [], ranked: [] },
  } }))

  await page.goto('/')
  await page.getByRole('button', { name: 'Tìm khu vực có nhiều lượt đón' }).click()
  await expect(page.getByText('Đang hiển thị 3 khu vực')).toBeVisible()
  await expect(page.getByText('Khu vực 4:', { exact: false })).toHaveCount(0)
  await expect(page.locator('.hotspot-marker')).toHaveCount(3)

  await page.route('**/api/**', route => route.abort())
  await page.getByLabel('Số khu vực hiển thị').selectOption('4')

  await expect(page.getByText('Đang hiển thị 4 khu vực')).toBeVisible()
  await expect(page.getByText('Khu vực 4:', { exact: false })).toBeVisible()
  await expect(page.locator('.hotspot-marker')).toHaveCount(4)
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
  await page.getByRole('button', { name: 'Tìm khu vực có nhiều lượt đón' }).click()
  await page.getByLabel('Giờ bắt đầu').fill('19:00')

  await expect(page.getByText('7 lượt đón', { exact: false })).toBeVisible()
  await expect(page.getByText('Bạn đã thay đổi bộ lọc. Nhấn nút tìm kiếm để cập nhật kết quả.')).toBeVisible()
  await expect(page.getByText('Brooklyn · Thứ Sáu · 18:00–19:00')).toBeVisible()
})

test('preview places pickup samples on an interactive map', async ({ page }) => {
  await page.route('**/api/bootstrap', route => route.fulfill({ json: {
    areas: ['Brooklyn'], points: [[40.68, -73.94]],
  } }))
  await page.route('**/api/preview', route => route.fulfill({ json: {
    total_points: 1, available_matching_dates: 1,
    matching_dates: ['2024-01-05'], points: [[40.68, -73.94]],
  } }))
  await page.route('https://*.tile.openstreetmap.org/**', route => route.abort())

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
  await page.route('https://*.tile.openstreetmap.org/**', route => route.abort())

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
  await page.getByRole('button', { name: 'Xóa khu vực đã chọn' }).click()
  await expect(page.getByRole('button', { name: 'Tìm khu vực có nhiều lượt đón' })).toBeDisabled()
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
  await page.getByRole('button', { name: 'Tìm khu vực có nhiều lượt đón' }).click()

  await expect(page.getByText('Số khu vực tìm thấy: 2')).toBeVisible()
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
  await expect(page.getByRole('button', { name: 'Tìm khu vực có nhiều lượt đón' })).toBeDisabled()
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
  await page.getByRole('button', { name: 'Tìm khu vực có nhiều lượt đón' }).click()

  await expect(page.getByRole('alert')).toContainText('Không thể xử lý bộ lọc. Hãy kiểm tra khu vực, ngày và giờ rồi thử lại.')
})

test('network error is explained in Vietnamese', async ({ page }) => {
  await page.route('**/api/bootstrap', route => route.abort())

  await page.goto('/')

  await expect(page.getByRole('alert')).toContainText('Không kết nối được với máy chủ. Hãy kiểm tra mạng và thử lại.')
})

test('new preview and previous analysis keep separate maps', async ({ page }) => {
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
  await page.getByRole('button', { name: 'Tìm khu vực có nhiều lượt đón' }).click()
  await page.getByLabel('Giờ bắt đầu').fill('19:00')

  await expect(page.getByText('7 lượt đón', { exact: false })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Bản đồ các điểm đón khách' }).locator('path.leaflet-interactive')).toHaveCount(1)
  await expect(page.getByRole('region', { name: 'Bản đồ kết quả' }).locator('path.leaflet-interactive')).toHaveCount(1)
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
  await page.route('https://*.tile.openstreetmap.org/**', route => route.abort())

  await page.goto('/')
  await page.getByLabel('Khu vực hành chính', { exact: true }).selectOption('EWR')

  const map = page.getByRole('region', { name: 'Bản đồ các điểm đón khách' })
  await map.scrollIntoViewIfNeeded()
  await expect(map.locator('path.leaflet-interactive')).toBeInViewport()
})

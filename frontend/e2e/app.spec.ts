import { createProject, expect, test } from './support'

test('display settings persist after a reload', async ({ page }) => {
  await page.goto('/#/settings/display')
  const html = page.locator('html')
  await page.getByRole('combobox', { name: 'Theme', exact: true }).selectOption('light')
  await expect(html).toHaveAttribute('data-theme', 'light')
  await page.reload()
  await expect(html).toHaveAttribute('data-theme', 'light')
  await expect(page.getByRole('combobox', { name: 'Theme', exact: true })).toHaveValue('light')

  await page.getByRole('combobox', { name: 'Theme', exact: true }).selectOption('dark')
  await expect(html).toHaveAttribute('data-theme', 'dark')
  await page.getByRole('combobox', { name: 'Theme', exact: true }).selectOption('system')
})

test('the command palette and shortcut sheet work from the keyboard', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Projects' })).toBeVisible()

  await page.keyboard.press('Control+k')
  const palette = page.getByRole('dialog', { name: 'Command palette' })
  await expect(palette).toBeVisible()
  await page.keyboard.type('diagnostics')
  await page.keyboard.press('Enter')
  await expect(palette).toBeHidden()
  await expect(page).toHaveURL(/#\/diagnostics/)

  await page.keyboard.press('?')
  const shortcuts = page.getByRole('dialog', { name: 'Keyboard shortcuts' })
  await expect(shortcuts).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(shortcuts).toBeHidden()
})

test('diagnostics reports optional models exactly as the backend sees them', async ({ page, request }) => {
  const { models } = (await (await request.get('/api/system/models')).json()) as {
    models: { name: string; available: boolean; version: string | null }[]
  }
  expect(models.length).toBeGreaterThan(0)
  await page.goto('/#/diagnostics')
  await page.getByRole('tab', { name: 'Models' }).click()
  for (const model of models) {
    const row = page.getByRole('row').filter({ hasText: model.name })
    await expect(row).toContainText(model.available ? (model.version ?? 'available') : 'not installed')
  }
})

test('a file that is not audio is rejected with an explanation', async ({ page, request, consoleGuard }) => {
  consoleGuard.allow(/Failed to load resource/)
  const projectId = await createProject(request, 'Broken import')
  await page.goto(`/#/p/${projectId}/compare`)
  await page.getByRole('button', { name: 'Import reference' }).first().click()
  const dialog = page.getByRole('dialog', { name: 'Import reference vocal' })
  await dialog
    .locator('input[type="file"]')
    .setInputFiles({ name: 'notes.wav', mimeType: 'audio/wav', buffer: Buffer.from('these are not samples') })
  await dialog.getByRole('button', { name: /^Import/ }).click()
  const alert = page.getByRole('alert')
  await expect(alert).toBeVisible()
  await expect(alert).toContainText(/decode|read|audio/i)
  await expect(page.getByText('Start with the reference vocal')).toBeVisible()
})

test('pages stay usable on a narrow window', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  for (const hash of ['#/', '#/settings', '#/diagnostics', '#/help', '#/calibration', '#/profiles']) {
    await page.goto(`/${hash}`)
    await page.waitForLoadState('networkidle')
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
    expect(overflow, `horizontal overflow on ${hash}`).toBeLessThanOrEqual(1)
  }
})

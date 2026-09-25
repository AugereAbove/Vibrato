import { createProject, expect, REFERENCE, TAKE, test } from './support'

test.describe.configure({ mode: 'serial' })

let projectId = ''

test('imports a reference and a take, then coaches the biggest difference', async ({ page, request }) => {
  test.setTimeout(300_000)
  projectId = await createProject(request, 'Imported song')
  await page.goto(`/#/p/${projectId}/compare`)

  await page.getByRole('button', { name: 'Import reference' }).first().click()
  const referenceDialog = page.getByRole('dialog', { name: 'Import reference vocal' })
  await referenceDialog.getByLabel('Lyrics (optional)').fill('la la la\nla la la')
  await referenceDialog
    .locator('input[type="file"]')
    .setInputFiles({ name: 'reference.wav', mimeType: 'audio/wav', buffer: REFERENCE() })
  await expect(referenceDialog.getByLabel('Name')).toHaveValue('reference')
  await expect(referenceDialog.getByLabel('Lyrics (optional)')).toHaveValue('la la la\nla la la')
  await referenceDialog.getByRole('button', { name: /^Import/ }).click()

  await expect(page.getByText('Now sing it yourself.')).toBeVisible({ timeout: 120_000 })

  await page.getByRole('button', { name: 'Import take' }).first().click()
  const takeDialog = page.getByRole('dialog', { name: 'Import your take' })
  await takeDialog
    .locator('input[type="file"]')
    .setInputFiles({ name: 'take-1.wav', mimeType: 'audio/wav', buffer: TAKE() })
  await takeDialog.getByRole('button', { name: /^Import/ }).click()

  await expect(page.getByRole('heading', { name: 'Your biggest differences in this take' })).toBeVisible({
    timeout: 180_000,
  })
  await expect(page.getByRole('img', { name: /^Overall score \d+ out of 100/ })).toBeVisible()

  await page.getByRole('button', { name: 'What should I fix next?' }).click()
  await expect(page.getByRole('button', { name: 'Clear loop' })).toBeVisible()
})

test('plays the reference and the take in sync', async ({ page }) => {
  await page.goto(`/#/p/${projectId}/compare`)
  await expect(page.getByRole('heading', { name: 'Your biggest differences in this take' })).toBeVisible()
  const transport = page.getByRole('contentinfo', { name: 'Transport' })
  await expect(transport.getByRole('button', { name: 'Play' })).toBeEnabled()

  await page.locator('body').press('Space')
  await expect(transport.getByRole('button', { name: 'Pause' })).toBeVisible()
  await expect(transport.getByLabel('Playback position')).not.toHaveText(/^0:00\.00/, { timeout: 5_000 })

  await page.locator('body').press('a')
  await page.locator('body').press('Space')
  await expect(transport.getByRole('button', { name: 'Play' })).toBeVisible()

  await transport.getByRole('radio', { name: /take/i }).click()
  await expect(transport.getByRole('radio', { name: /take/i })).toBeChecked()
})

test('shows measurements in analyst mode and explains a region', async ({ page }) => {
  await page.goto(`/#/p/${projectId}/compare`)
  await page.getByRole('radio', { name: 'Analyst' }).click()
  for (const tab of ['Heatmap', 'Measurements', 'Scores']) {
    await page.getByRole('tab', { name: new RegExp(`^${tab}`) }).click()
    await expect(page.getByRole('tab', { name: new RegExp(`^${tab}`) })).toHaveAttribute(
      'aria-selected',
      'true',
    )
  }

  const waveform = page.locator('.lane-body-waveform').first()
  const box = await waveform.boundingBox()
  if (!box) throw new Error('waveform lane is not visible')
  await page.mouse.move(box.x + box.width * 0.25, box.y + box.height / 2)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width * 0.55, box.y + box.height / 2, { steps: 8 })
  await page.mouse.up()

  await page.getByRole('button', { name: 'Why does it sound different?' }).click()
  const why = page.getByRole('dialog')
  await expect(why).toBeVisible()
  await expect(why.locator('.why-body')).toBeVisible({ timeout: 60_000 })
  await page.keyboard.press('Escape')
  await expect(why).toBeHidden()
  await page.getByRole('radio', { name: 'Coach' }).click()
})

test('records a take from the microphone', async ({ page }) => {
  test.setTimeout(240_000)
  await page.goto(`/#/p/${projectId}/compare`)
  await page.getByRole('button', { name: 'Record a take' }).click()
  const dialog = page.getByRole('dialog', { name: 'Record a take' })
  const start = dialog.getByRole('button', { name: 'Start recording' })
  await expect(start).toBeEnabled({ timeout: 20_000 })
  await start.click()
  await expect(dialog.locator('.recording-status')).toBeVisible({ timeout: 15_000 })
  await page.waitForTimeout(2_500)
  await page.getByRole('button', { name: 'Stop recording' }).click()

  const review = page.getByRole('dialog', { name: 'Review your take' })
  await expect(review).toBeVisible()
  await review.getByRole('button', { name: 'Keep and analyse' }).click()
  await expect(review).toBeHidden({ timeout: 30_000 })
  const navigation = page.getByRole('navigation', { name: 'Project navigation' })
  await expect(navigation.getByRole('button', { name: /Take 2 recorded/ })).toBeVisible({ timeout: 30_000 })
  await expect(navigation.getByText('Comparing Take 2')).toBeHidden({ timeout: 180_000 })
  await page.screenshot({ path: test.info().outputPath('recorded.png') })
})

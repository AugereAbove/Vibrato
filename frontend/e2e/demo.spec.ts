import { expect, test } from './support'

test('the demo project builds and shows the planted differences', async ({ page }) => {
  test.setTimeout(600_000)
  await page.goto('/')
  await page.getByRole('button', { name: 'Explore the demo project' }).click()
  await expect(page).toHaveURL(/#\/p\//, { timeout: 540_000 })
  await expect(page.getByRole('heading', { name: 'Your biggest differences in this take' })).toBeVisible({
    timeout: 60_000,
  })
  await expect(page.locator('.finding-card').first()).toBeVisible()

  await page.getByRole('button', { name: 'What should I fix next?' }).click()
  await expect(page.getByRole('button', { name: 'Clear loop' })).toBeVisible()

  await page.getByRole('radio', { name: 'Research' }).click()
  await expect(page.locator('.lane-body-spectrogram').first()).toBeVisible()
  await page.getByRole('radio', { name: 'Coach' }).click()

  await page
    .getByRole('navigation', { name: 'Project views' })
    .getByRole('button', { name: 'Progress' })
    .click()
  await expect(page).toHaveURL(/\/progress/)
})

import { createProject, expect, test } from './support'

test('first visit explains the app and creates a project', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('Welcome to Vibrato')).toBeVisible()
  await expect(page.getByText(/no accounts, no uploads/)).toBeVisible()

  await page.getByRole('button', { name: 'New project' }).first().click()
  const dialog = page.getByRole('dialog', { name: 'New project' })
  await expect(dialog.getByRole('button', { name: 'Create project' })).toBeDisabled()
  await dialog.getByLabel('Project name').fill('Autumn Leaves')
  await dialog.getByLabel('Artist').fill('Test Singer')
  await dialog.getByRole('button', { name: 'Create project' }).click()

  await expect(page).toHaveURL(/#\/p\/[^/]+\/compare/)
  await expect(page.getByText('Start with the reference vocal')).toBeVisible()

  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Open Autumn Leaves' })).toBeVisible()
})

test('projects can be searched and favourited', async ({ page, request }) => {
  await createProject(request, 'Blue Moon')
  await createProject(request, 'Fly Me to the Moon')
  await createProject(request, 'Summertime')
  await page.goto('/')

  await page.getByLabel('Search projects').fill('moon')
  await expect(page.getByRole('button', { name: 'Open Blue Moon' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Open Fly Me to the Moon' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Open Summertime' })).toBeHidden()

  await page.getByLabel('Search projects').fill('')
  await page
    .locator('.project-card', { has: page.getByRole('button', { name: 'Open Summertime' }) })
    .getByRole('button', { name: 'Add to favourites' })
    .click()
  await page.getByRole('radio', { name: 'Favourites' }).click()
  await expect(page.getByRole('button', { name: 'Open Summertime' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Open Blue Moon' })).toBeHidden()
})

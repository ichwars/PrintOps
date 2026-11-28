import { beforeEach, describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import { SettingsPage } from '../../pages/SettingsPage';
import { render } from '../utils';
import { resetSettingsPage, setSettingsTabUrl } from './settingsPageFixtures';

describe('settings sub-navigation', () => {
  beforeEach(resetSettingsPage);

  it.each([
    ['integrations', 'Integrations'],
    ['operations', 'Operations'],
  ])('uses the shared responsive settings navigation in %s', async (tab, label) => {
    setSettingsTabUrl(tab);
    render(<SettingsPage />);

    const navigation = await screen.findByRole('navigation', { name: label });
    expect(navigation.parentElement).toHaveClass(
      'max-md:[&>[role=navigation]]:grid-cols-2',
      '[&_button[aria-current=page]]:text-accent-foreground',
    );
  });
});

import fs from 'node:fs';
import path from 'node:path';
import * as ts from 'typescript';
import { describe, expect, it } from 'vitest';

const groups = {
  settings: [
    'pages/CameraTokensPage.tsx',
    'pages/LibraryTrashPage.tsx',
    'pages/SettingsPage.tsx',
    'components/AddNotificationModal.tsx',
    'components/AddSmartPlugModal.tsx',
    'components/EmailSettings.tsx',
    'components/FailureDetectionSettings.tsx',
    'components/GitHubBackupSettings.tsx',
    'components/SmartPlugCard.tsx',
    'components/settings/BusinessProfileEditorModal.tsx',
    'components/settings/DeviceManagement.tsx',
  ],
  printerAndProjects: [
    'pages/MaintenancePage.tsx',
    'pages/PrintersPage.tsx',
    'pages/ProjectsPage.tsx',
    'pages/ProjectDetailPage.tsx',
    'pages/spoolbuddy/SpoolBuddyWriteTagPage.tsx',
    'components/PreheatFilamentTargetsEditor.tsx',
    'components/PrintModal/index.tsx',
    'components/PrintModal/PrintOptions.tsx',
    'components/PrintModal/ScheduleOptions.tsx',
    'components/RunWithPipelineModal.tsx',
  ],
  inventoryAndHistory: [
    'components/AMSHistoryModal.tsx',
    'components/BulkEditSpoolsModal.tsx',
    'components/CameraWall.tsx',
    'components/EditArchiveModal.tsx',
    'components/ForecastPanel.tsx',
    'components/HeaterHistoryModal.tsx',
    'components/PurgeArchivesModal.tsx',
    'components/PurgeOldFilesModal.tsx',
    'components/SpoolCatalogSettings.tsx',
    'components/spool-form/AdditionalSection.tsx',
    'components/spool-form/FilamentSection.tsx',
  ],
};

const sourceRoot = path.resolve(process.cwd(), 'src');

function directNumericFields(file: string, source: string): string[] {
  const sourceFile = ts.createSourceFile(
    file,
    source,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX,
  );
  const matches: string[] = [];

  function visit(node: ts.Node): void {
    if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) {
      const tagName = node.tagName.getText(sourceFile);
      if (tagName === 'input' || tagName === 'TextField') {
        const typeAttribute = node.attributes.properties.find(
          (property): property is ts.JsxAttribute =>
            ts.isJsxAttribute(property) && property.name.getText(sourceFile) === 'type',
        );
        const initializer = typeAttribute?.initializer;
        const numberLiteral =
          initializer &&
          ((ts.isStringLiteral(initializer) && initializer.text === 'number') ||
            (ts.isJsxExpression(initializer) &&
              initializer.expression &&
              ts.isStringLiteral(initializer.expression) &&
              initializer.expression.text === 'number'));
        if (numberLiteral) {
          const { line } = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile));
          matches.push(`${file}:${line + 1}`);
        }
      }
    }
    ts.forEachChild(node, visit);
  }

  visit(sourceFile);
  return matches;
}

describe('NumberField migration', () => {
  it.each(Object.entries(groups))('%s uses NumberField for rendered numeric inputs', (_group, files) => {
    for (const file of files) {
      const source = fs.readFileSync(path.join(sourceRoot, file), 'utf8');
      expect(directNumericFields(file, source), file).toEqual([]);
    }
  });

  it('uses NumberField for dynamic numeric notification fields', () => {
    const source = fs.readFileSync(
      path.join(sourceRoot, 'components/AddNotificationModal.tsx'),
      'utf8',
    );
    expect(source).toMatch(/field\.type === 'number'[\s\S]*?<NumberField/);
  });

  it('uses NumberField for dynamic numeric bulk-edit fields', () => {
    const source = fs.readFileSync(
      path.join(sourceRoot, 'components/BulkEditSpoolsModal.tsx'),
      'utf8',
    );
    expect(source).toMatch(/f\.type === 'number'[\s\S]*?<NumberField/);
  });
});

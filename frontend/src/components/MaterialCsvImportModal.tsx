import { useRef, useState, type ChangeEvent, type DragEvent } from 'react';
import { AlertTriangle, CheckCircle, FileText, Loader2, MinusCircle, Upload, X, XCircle } from 'lucide-react';

import { smallPartsApi, type SmallPartCsvImportPreview, type SmallPartCsvImportRow } from '../api/smallParts';
import { Button, FileInput } from './ui';

interface MaterialCsvImportModalProps {
  onClose: () => void;
  onImported: (created: number, updated: number) => void;
}

export function MaterialCsvImportModal({ onClose, onImported }: MaterialCsvImportModalProps) {
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [preview, setPreview] = useState<SmallPartCsvImportPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function loadPreview(selected: File) {
    setFile(selected);
    setPreview(null);
    setError(null);
    setLoading(true);
    try {
      setPreview(await smallPartsApi.importCsvPreview(selected));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'CSV-Datei konnte nicht gelesen werden.');
    } finally {
      setLoading(false);
    }
  }

  function handleFileSelect(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0];
    if (selected) void loadPreview(selected);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragging(false);
    const selected = event.dataTransfer.files?.[0];
    if (selected) void loadPreview(selected);
  }

  async function handleImport() {
    if (!file || importing) return;
    setImporting(true);
    setError(null);
    try {
      const result = await smallPartsApi.importCsv(file);
      if (result.errors > 0) {
        const first = result.error_rows[0];
        setError(first ? `Import abgebrochen: Zeile ${first.row_number}: ${first.reason}` : 'Import abgebrochen.');
        return;
      }
      onImported(result.created, result.updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import fehlgeschlagen.');
    } finally {
      setImporting(false);
    }
  }

  function statusIcon(row: SmallPartCsvImportRow) {
    if (row.status === 'valid' && row.action === 'update') {
      return <CheckCircle className="h-4 w-4 flex-shrink-0 text-sky-400" />;
    }
    if (row.status === 'valid') return <CheckCircle className="h-4 w-4 flex-shrink-0 text-bambu-green" />;
    if (row.status === 'error') return <XCircle className="h-4 w-4 flex-shrink-0 text-red-400" />;
    return <MinusCircle className="h-4 w-4 flex-shrink-0 text-bambu-gray" />;
  }

  const validCount = preview?.valid_count ?? 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-lg border border-bambu-dark-tertiary bg-bambu-dark-secondary">
        <div className="flex items-center justify-between border-b border-bambu-dark-tertiary p-4">
          <h2 className="text-lg font-semibold text-white">Material aus CSV importieren</h2>
          <button type="button" onClick={onClose} className="rounded p-1 hover:bg-bambu-dark" aria-label="Schließen">
            <X className="h-5 w-5 text-bambu-gray" />
          </button>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto p-4">
          <div
            onDragOver={(event) => {
              event.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={(event) => {
              event.preventDefault();
              setIsDragging(false);
            }}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`cursor-pointer rounded-lg border-2 border-dashed p-6 text-center transition-colors ${
              isDragging ? 'border-bambu-green bg-bambu-green/10' : 'border-bambu-dark-tertiary hover:border-bambu-green/50'
            }`}
          >
            <Upload className={`mx-auto mb-2 h-9 w-9 ${isDragging ? 'text-bambu-green' : 'text-bambu-gray'}`} />
            {file ? (
              <p className="flex items-center justify-center gap-2 font-medium text-white">
                <FileText className="h-4 w-4" /> {file.name}
              </p>
            ) : (
              <>
                <p className="font-medium text-white">CSV-Datei auswählen oder hier ablegen</p>
                <p className="mt-1 text-xs text-bambu-gray/70">Kopfzeile: Artikelnummer, Bezeichnung, Einheit, Physisch, Mindestbestand, Einzelpreis...</p>
              </>
            )}
          </div>
          <FileInput ref={fileInputRef} aria-label="CSV-Datei" accept=".csv,text/csv" className="hidden" onChange={handleFileSelect} />

          {loading ? (
            <div className="flex items-center justify-center gap-2 py-4 text-bambu-gray">
              <Loader2 className="h-4 w-4 animate-spin" /> Datei wird gelesen...
            </div>
          ) : null}

          {error ? (
            <div className="flex items-start gap-3 rounded-lg border border-red-500/30 bg-red-500/10 p-3">
              <XCircle className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-400" />
              <p className="break-words text-sm text-red-300">{error}</p>
            </div>
          ) : null}

          {preview ? (
            <>
              <div className="flex flex-wrap gap-3 text-sm">
                <span className="rounded bg-bambu-green/10 px-2 py-1 text-bambu-green">{preview.valid_count} gültig</span>
                <span className="rounded bg-red-500/10 px-2 py-1 text-red-300">{preview.error_count} Fehler</span>
                <span className="rounded bg-bambu-dark px-2 py-1 text-bambu-gray">{preview.skipped_count} übersprungen</span>
              </div>

              {preview.warnings.length > 0 ? (
                <div className="space-y-1 rounded-lg border border-yellow-500/30 bg-yellow-500/10 p-3">
                  {preview.warnings.map((warning, index) => (
                    <p key={`${warning}-${index}`} className="flex items-start gap-2 text-xs text-yellow-300">
                      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" /> {warning}
                    </p>
                  ))}
                </div>
              ) : null}

              <div className="overflow-hidden rounded-lg border border-bambu-dark-tertiary">
                <div className="max-h-72 overflow-y-auto">
                  <table className="w-full text-sm">
                    <thead className="sticky top-0 bg-bambu-dark">
                      <tr className="text-left text-bambu-gray">
                        <th className="px-3 py-2 font-medium">Zeile</th>
                        <th className="px-3 py-2 font-medium">Status</th>
                        <th className="px-3 py-2 font-medium">Artikelnummer</th>
                        <th className="px-3 py-2 font-medium">Bezeichnung</th>
                        <th className="px-3 py-2 font-medium">Bestand</th>
                      </tr>
                    </thead>
                    <tbody>
                      {preview.rows.map((row) => (
                        <tr key={row.row_number} className="border-t border-bambu-dark-tertiary">
                          <td className="px-3 py-2 text-bambu-gray">{row.row_number}</td>
                          <td className="px-3 py-2">
                            <div className="flex items-center gap-1.5">
                              {statusIcon(row)}
                              <span className="text-xs text-bambu-gray-light">
                                {row.reason ?? (row.action === 'update' ? 'Aktualisieren' : 'Anlegen')}
                              </span>
                            </div>
                          </td>
                          <td className="px-3 py-2 font-mono text-white">{row.sku || '-'}</td>
                          <td className="px-3 py-2 text-white">{row.name || '-'}</td>
                          <td className="px-3 py-2 text-bambu-gray-light">{row.opening_quantity || '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          ) : null}
        </div>

        <div className="flex justify-end gap-2 border-t border-bambu-dark-tertiary p-4">
          <Button type="button" variant="secondary" onClick={onClose} disabled={importing}>
            Abbrechen
          </Button>
          <Button type="button" onClick={handleImport} disabled={!preview || validCount === 0 || preview.error_count > 0 || importing}>
            {importing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            {validCount > 0 ? `${validCount} Zeilen importieren` : 'Keine gültigen Zeilen'}
          </Button>
        </div>
      </div>
    </div>
  );
}

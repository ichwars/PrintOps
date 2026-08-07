import { AlertTriangle, CheckCircle, Flame, Loader2, Pencil, ScanSearch, X, XCircle } from 'lucide-react';
import { api } from '../../api/client';
import { parseUTCDate } from '../../utils/date';
import { Button } from '../../components/Button';
import { ConfirmModal } from '../../components/ConfirmModal';
import { FileManagerModal } from '../../components/FileManagerModal';
import { MQTTDebugModal } from '../../components/MQTTDebugModal';
import { HMSErrorModal } from '../../components/HMSErrorModal';
import { AMSHistoryModal } from '../../components/AMSHistoryModal';
import { AmsBackupModal } from '../../components/AmsBackupModal';
import { HeaterHistoryModal } from '../../components/HeaterHistoryModal';
import { LinkSpoolModal } from '../../components/LinkSpoolModal';
import { AssignSpoolModal } from '../../components/AssignSpoolModal';
import { ConfigureAmsSlotModal } from '../../components/ConfigureAmsSlotModal';
import { SkipObjectsModal } from '../../components/SkipObjectsModal';
import { FileUploadModal } from '../../components/FileUploadModal';
import { PrintModal } from '../../components/PrintModal';
import { PrinterInfoModal } from '../../components/PrinterInfoModal';
import { ConnectionDiagnosticModal } from '../../components/ConnectionDiagnostic';
import { NumberField, Slider, TextField } from '../../components/ui';
import { mapModelCode } from './printer-status';
import { ToolbarDropdown } from './printer-toolbar';
import { EditPrinterModal } from './EditPrinterModal';
import { FirmwareUpdateModal } from './FirmwareUpdateModal';
import type { usePrinterCardModel } from './usePrinterCardModel';

type PrinterCardModel = NonNullable<ReturnType<typeof usePrinterCardModel>>;

interface PrinterCardOverlaysProps {
  model: PrinterCardModel;
}

export function PrinterCardOverlays({ model }: PrinterCardOverlaysProps) {
  const {
    printer, maintenanceInfo, amsThresholds, spoolmanEnabled,
    dryingPresets, t, queryClient, hasPermission,
    showEditModal, setShowEditModal, showFileManager, setShowFileManager,
    showMQTTDebug, setShowMQTTDebug, showPowerOnConfirm, setShowPowerOnConfirm,
    showPowerOffConfirm, setShowPowerOffConfirm, haToggleConfirm, setHaToggleConfirm,
    showHMSModal, setShowHMSModal, amsBackupModalOpen, setAmsBackupModalOpen,
    showStopConfirm, setShowStopConfirm, showPauseConfirm, setShowPauseConfirm,
    showNotHomedModal, setShowNotHomedModal, showResumeConfirm, setShowResumeConfirm,
    showSkipObjectsModal, setShowSkipObjectsModal, showUploadForPrint, setShowUploadForPrint,
    showPrinterInfo, showDiagnostic, setShowDiagnostic, closePrinterInfo,
    printAfterUpload, setPrintAfterUpload, dryingPopoverAmsId, setDryingPopoverAmsId,
    dryingPopoverModuleType, dryingFilament, setDryingFilament, dryingTemp,
    setDryingTemp, dryingDuration, setDryingDuration, dryingRotateTray,
    setDryingRotateTray, dryingPopoverPos, amsHistoryModal, setAmsHistoryModal,
    heaterHistoryModal, setHeaterHistoryModal, linkSpoolModal, setLinkSpoolModal,
    assignSpoolModal, setAssignSpoolModal, configureSlotModal, setConfigureSlotModal,
    showFirmwareModal, setShowFirmwareModal, plateCheckResult, isCalibrating,
    editingRoi, setEditingRoi, isSavingRoi, status,
    firmwareInfo, amsData,
    runoutGuidance, smartPlug, canUsePrinterControl, startDryingMutation,
    setAmsBackupMutation, powerControlMutation, runScriptMutation, stopPrintMutation,
    pausePrintMutation, resumePrintMutation, bedJogMutation, homeAxesMutation,
    maintenanceMutation, confirmMaintenanceEnter, setConfirmMaintenanceEnter, plateReferences,
    editingRefLabel, setEditingRefLabel, closePlateCheckModal, handleCalibratePlate,
    handleUpdateRefLabel, handleDeleteRef, handleSaveRoi,
  } = model;

  return (
    <>
    {/* File Manager Modal */}
    {showFileManager && (
      <FileManagerModal
        printerId={printer.id}
        printerName={printer.name}
        onClose={() => setShowFileManager(false)}
      />
    )}

    {/* Upload for Print Modal */}
    {showUploadForPrint && (
      <FileUploadModal
        folderId={null}
        onClose={() => setShowUploadForPrint(false)}
        onUploadComplete={() => {}}
        autoUpload
        accept=".gcode,.3mf"
        validateFile={(file) => {
          const lower = file.name.toLowerCase();
          if (!lower.endsWith('.gcode') && !lower.includes('.gcode.')) {
            return t('printers.dropNotPrintable', 'Only .gcode and .gcode.3mf files can be printed');
          }
        }}
        onFileUploaded={(uploadedFile) => {
          // Check printer compatibility if sliced_for_model is available in metadata
          const slicedFor = (uploadedFile.metadata as Record<string, unknown>)?.sliced_for_model as string | undefined;
          const printerModel = mapModelCode(printer.model);
          if (slicedFor && printerModel && slicedFor.toLowerCase() !== printerModel.toLowerCase()) {
            api.deleteLibraryFile(uploadedFile.id).catch(() => {});
            return t('printers.incompatibleFile', 'This file was sliced for {{slicedFor}}, but this printer is a {{printerModel}}', { slicedFor, printerModel });
          }
          setPrintAfterUpload({ id: uploadedFile.id, filename: uploadedFile.filename });
        }}
      />
    )}

    {/* Print Modal (after upload) */}
    {printAfterUpload && (
      <PrintModal
        mode="create"
        libraryFileId={printAfterUpload.id}
        archiveName={printAfterUpload.filename}
        initialSelectedPrinterIds={[printer.id]}
        onClose={() => setPrintAfterUpload(null)}
        onSuccess={() => setPrintAfterUpload(null)}
        cleanupLibraryAfterDispatch
      />
    )}

    {/* MQTT Debug Modal */}
    {showMQTTDebug && (
      <MQTTDebugModal
        printerId={printer.id}
        printerName={printer.name}
        onClose={() => setShowMQTTDebug(false)}
      />
    )}

    {showDiagnostic && (
      <ConnectionDiagnosticModal
        printerId={printer.id}
        printerName={printer.name}
        onClose={() => setShowDiagnostic(false)}
      />
    )}

    {showPrinterInfo && (
      <PrinterInfoModal
        printer={printer}
        status={status}
        totalPrintHours={maintenanceInfo?.total_print_hours}
        onClose={closePrinterInfo}
      />
    )}

    {/* Plate Check Result Modal */}
    {plateCheckResult && (
      <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={() => closePlateCheckModal()}>
        <div className="bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded-xl shadow-2xl max-w-lg w-full" onClick={e => e.stopPropagation()}>
          <div className="flex items-center justify-between p-4 border-b border-bambu-dark-tertiary">
            <div className="flex items-center gap-2">
              {plateCheckResult.needs_calibration ? (
                <ScanSearch className="w-5 h-5 text-blue-500" />
              ) : plateCheckResult.is_empty ? (
                <CheckCircle className="w-5 h-5 text-green-500" />
              ) : (
                <XCircle className="w-5 h-5 text-yellow-500" />
              )}
              <h2 className="text-lg font-semibold text-white">
                Build Plate Check
              </h2>
              {plateCheckResult.reference_count !== undefined && plateCheckResult.max_references && (
                <span className="text-xs text-bambu-gray bg-bambu-dark-tertiary px-2 py-1 rounded">
                  {plateCheckResult.reference_count}/{plateCheckResult.max_references} refs
                </span>
              )}
            </div>
            <button
              onClick={() => closePlateCheckModal()}
              className="p-1 text-bambu-gray hover:text-white rounded transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
          <div className="p-4 space-y-4">
            {plateCheckResult.needs_calibration ? (
              <>
                <div className="p-3 rounded-lg bg-blue-100 dark:bg-blue-500/20 border border-blue-300 dark:border-blue-500/50">
                  <p className="font-medium text-blue-700 dark:text-blue-400">
                    {t('printers.plateDetection.calibrationRequired')}
                  </p>
                  <p className="text-sm text-bambu-gray mt-1" dangerouslySetInnerHTML={{ __html: t('printers.plateDetection.calibrationInstructions') }} />
                </div>
                <div className="text-sm text-bambu-gray space-y-2">
                  <p>{t('printers.plateDetection.calibrationDescription')}</p>
                  <p dangerouslySetInnerHTML={{ __html: t('printers.plateDetection.calibrationTip') }} />
                </div>
              </>
            ) : (
              <>
                <div className={`p-3 rounded-lg ${plateCheckResult.is_empty ? 'bg-green-100 dark:bg-green-500/20 border border-green-300 dark:border-green-500/50' : 'bg-yellow-100 dark:bg-yellow-500/20 border border-yellow-300 dark:border-yellow-500/50'}`}>
                  <p className={`font-medium ${plateCheckResult.is_empty ? 'text-green-700 dark:text-green-400' : 'text-yellow-700 dark:text-yellow-400'}`}>
                    {plateCheckResult.is_empty ? t('printers.plateDetection.plateEmpty') : t('printers.plateDetection.objectsDetected')}
                  </p>
                  <p className="text-sm text-bambu-gray mt-1">
                    {t('printers.plateDetection.confidence')}: {Math.round(plateCheckResult.confidence * 100)}% | {t('printers.plateDetection.difference')}: {plateCheckResult.difference_percent.toFixed(1)}%
                  </p>
                </div>
                {plateCheckResult.debug_image_url && (
                  <div>
                    <p className="text-sm text-bambu-gray mb-2">{t('printers.plateDetection.analysisPreview')}</p>
                    <img
                      src={plateCheckResult.debug_image_url}
                      alt={t('printers.plateDetection.analysisPreview')}
                      className="w-full rounded-lg border border-bambu-dark-tertiary"
                    />
                    <p className="text-xs text-bambu-gray mt-2">
                      {t('printers.plateDetection.analysisLegend')}
                    </p>
                  </div>
                )}
                <p className="text-xs text-bambu-gray">
                  {plateCheckResult.message}
                </p>
              </>
            )}

            {/* Saved References Grid */}
            {plateReferences && plateReferences.references.length > 0 && (
              <div className="mt-4">
                <div className="flex items-center gap-2 mb-2">
                  <p className="text-sm font-medium text-white shrink-0">
                    {t('printers.plateDetection.savedReferences', { count: plateReferences.references.length, max: plateReferences.max_references })}
                  </p>
                  <div className="flex-1 h-[2px] bg-bambu-dark-tertiary" />
                </div>
                <div className="grid grid-cols-5 gap-2">
                  {plateReferences.references.map((ref) => (
                    <div key={ref.index} className="relative group">
                      <img
                        src={api.getPlateReferenceThumbnailUrl(printer.id, ref.index)}
                        alt={ref.label || `Reference ${ref.index + 1}`}
                        className="w-full aspect-video object-cover rounded border border-bambu-dark-tertiary"
                      />
                      {/* Delete button */}
                      <button
                        onClick={() => handleDeleteRef(ref.index)}
                        className="absolute top-1 right-1 p-0.5 bg-red-500/80 rounded opacity-0 group-hover:opacity-100 transition-opacity"
                        title={t('printers.plateDetection.deleteReference')}
                      >
                        <X className="w-3 h-3 text-white" />
                      </button>
                      {/* Label */}
                      {editingRefLabel?.index === ref.index ? (
                        <TextField
                          type="text"
                          value={editingRefLabel.label}
                          onChange={(e) => setEditingRefLabel({ ...editingRefLabel, label: e.target.value })}
                          onBlur={() => handleUpdateRefLabel(ref.index, editingRefLabel.label)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') handleUpdateRefLabel(ref.index, editingRefLabel.label);
                            if (e.key === 'Escape') setEditingRefLabel(null);
                          }}
                          className="w-full mt-1 px-1 py-0.5 text-xs bg-bambu-dark-tertiary border border-bambu-green rounded text-white"
                          autoFocus
                          placeholder={t('printers.plateDetection.labelPlaceholder')}
                        />
                      ) : (
                        <p
                          className="text-xs text-bambu-gray mt-1 truncate cursor-pointer hover:text-white"
                          onClick={() => setEditingRefLabel({ index: ref.index, label: ref.label })}
                          title={ref.label ? t('printers.plateDetection.clickToEdit', { label: ref.label }) : t('printers.plateDetection.clickToAddLabel')}
                        >
                          {ref.label || <span className="italic opacity-50">{t('printers.noLabel')}</span>}
                        </p>
                      )}
                      {/* Timestamp */}
                      <p className="text-[10px] text-bambu-gray/60">
                        {ref.timestamp ? parseUTCDate(ref.timestamp)?.toLocaleDateString() ?? '' : ''}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* ROI Editor */}
            {!plateCheckResult.needs_calibration && (
              <div className="mt-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex min-w-0 flex-1 items-center gap-2">
                    <p className="text-sm font-medium text-white shrink-0">{t('printers.roi.title')}</p>
                    <div className="flex-1 h-[2px] bg-bambu-dark-tertiary" />
                  </div>
                  {!editingRoi ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setEditingRoi(plateCheckResult.roi || { x: 0.15, y: 0.35, w: 0.70, h: 0.55 })}
                    >
                      <Pencil className="w-3 h-3 mr-1" />
                      {t('common.edit')}
                    </Button>
                  ) : (
                    <div className="flex gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setEditingRoi(null)}
                        disabled={isSavingRoi}
                      >
                        {t('common.cancel')}
                      </Button>
                      <Button
                        size="sm"
                        onClick={handleSaveRoi}
                        disabled={isSavingRoi}
                      >
                        {isSavingRoi ? <Loader2 className="w-3 h-3 animate-spin" /> : t('common.save')}
                      </Button>
                    </div>
                  )}
                </div>
                {editingRoi ? (
                  <div className="space-y-3 bg-bambu-dark-tertiary/50 p-3 rounded-lg">
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="text-xs text-bambu-gray">{t('printers.roi.xStart')}</label>
                        <Slider
                          min="0"
                          max="0.9"
                          step="0.01"
                          value={editingRoi.x}
                          onChange={(e) => setEditingRoi({ ...editingRoi, x: parseFloat(e.target.value) })}
                          className="w-full h-1.5 bg-bambu-dark-tertiary rounded-lg cursor-pointer accent-green-500"
                        />
                        <span className="text-xs text-bambu-gray">{Math.round(editingRoi.x * 100)}%</span>
                      </div>
                      <div>
                        <label className="text-xs text-bambu-gray">{t('printers.roi.yStart')}</label>
                        <Slider
                          min="0"
                          max="0.9"
                          step="0.01"
                          value={editingRoi.y}
                          onChange={(e) => setEditingRoi({ ...editingRoi, y: parseFloat(e.target.value) })}
                          className="w-full h-1.5 bg-bambu-dark-tertiary rounded-lg cursor-pointer accent-green-500"
                        />
                        <span className="text-xs text-bambu-gray">{Math.round(editingRoi.y * 100)}%</span>
                      </div>
                      <div>
                        <label className="text-xs text-bambu-gray">{t('printers.width')}</label>
                        <Slider
                          min="0.1"
                          max="1"
                          step="0.01"
                          value={editingRoi.w}
                          onChange={(e) => setEditingRoi({ ...editingRoi, w: parseFloat(e.target.value) })}
                          className="w-full h-1.5 bg-bambu-dark-tertiary rounded-lg cursor-pointer accent-green-500"
                        />
                        <span className="text-xs text-bambu-gray">{Math.round(editingRoi.w * 100)}%</span>
                      </div>
                      <div>
                        <label className="text-xs text-bambu-gray">{t('printers.height')}</label>
                        <Slider
                          min="0.1"
                          max="1"
                          step="0.01"
                          value={editingRoi.h}
                          onChange={(e) => setEditingRoi({ ...editingRoi, h: parseFloat(e.target.value) })}
                          className="w-full h-1.5 bg-bambu-dark-tertiary rounded-lg cursor-pointer accent-green-500"
                        />
                        <span className="text-xs text-bambu-gray">{Math.round(editingRoi.h * 100)}%</span>
                      </div>
                    </div>
                    <p className="text-xs text-bambu-gray">
                      {t('printers.roi.instruction')}
                    </p>
                  </div>
                ) : (
                  <p className="text-xs text-bambu-gray">
                    Current: X={Math.round((plateCheckResult.roi?.x || 0.15) * 100)}%, Y={Math.round((plateCheckResult.roi?.y || 0.35) * 100)}%,
                    W={Math.round((plateCheckResult.roi?.w || 0.70) * 100)}%, H={Math.round((plateCheckResult.roi?.h || 0.55) * 100)}%
                  </p>
                )}
              </div>
            )}
          </div>
          <div className="flex justify-end gap-2 p-4">
            {plateCheckResult.needs_calibration ? (
              <>
                <Button variant="ghost" onClick={() => closePlateCheckModal()}>
                  {t('common.cancel')}
                </Button>
                <Button
                  onClick={() => handleCalibratePlate()}
                  disabled={isCalibrating}
                >
                  {isCalibrating ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      Calibrating...
                    </>
                  ) : (
                    'Calibrate Empty Plate'
                  )}
                </Button>
              </>
            ) : (
              <>
                <Button variant="ghost" onClick={() => handleCalibratePlate()} disabled={isCalibrating}>
                  {isCalibrating ? 'Adding...' : `Add Reference (${plateReferences?.references.length || 0}/${plateReferences?.max_references || 5})`}
                </Button>
                <Button onClick={() => closePlateCheckModal()}>
                  Close
                </Button>
              </>
            )}
          </div>
        </div>
      </div>
    )}

    {/* Power On Confirmation */}
    {showPowerOnConfirm && smartPlug && (
      <ConfirmModal
        title={t('printers.confirm.powerOnTitle')}
        message={t('printers.confirm.powerOnMessage', { name: printer.name })}
        confirmText={t('printers.confirm.powerOnButton')}
        variant="default"
        onConfirm={() => {
          powerControlMutation.mutate('on');
          setShowPowerOnConfirm(false);
        }}
        onCancel={() => setShowPowerOnConfirm(false)}
      />
    )}

    {/* Maintenance Mode mid-print confirmation (#1476) — entering maintenance
        disconnects MQTT, which stops progress tracking + completion
        notifications for the in-flight job. Idle / FINISH / FAILED states
        skip this dialog and toggle directly. */}
    {confirmMaintenanceEnter && (
      <ConfirmModal
        title={t('printers.maintenance.confirmMidPrintTitle')}
        message={t('printers.maintenance.confirmMidPrintMessage', { name: printer.name })}
        confirmText={t('printers.maintenance.menuEnter')}
        variant="danger"
        onConfirm={() => {
          maintenanceMutation.mutate(false);
          setConfirmMaintenanceEnter(false);
        }}
        onCancel={() => setConfirmMaintenanceEnter(false)}
      />
    )}

    {/* Power Off Confirmation */}
    {showPowerOffConfirm && smartPlug && (
      <ConfirmModal
        title={t('printers.confirm.powerOffTitle')}
        message={
          status?.state === 'RUNNING'
            ? t('printers.confirm.powerOffWarning', { name: printer.name })
            : t('printers.confirm.powerOffMessage', { name: printer.name })
        }
        confirmText={t('printers.confirm.powerOffButton')}
        variant="danger"
        onConfirm={() => {
          powerControlMutation.mutate('off');
          setShowPowerOffConfirm(false);
        }}
        onCancel={() => setShowPowerOffConfirm(false)}
      />
    )}

    {/* HA entity toggle confirmation (Show on Printer Card switches) */}
    {haToggleConfirm && (
      <ConfirmModal
        title={t('printers.confirm.haToggleTitle', { name: haToggleConfirm.name })}
        message={
          status?.state === 'RUNNING'
            ? t('printers.confirm.haToggleWarning', { name: printer.name, entity: haToggleConfirm.ha_entity_id || haToggleConfirm.name })
            : t('printers.confirm.haToggleMessage', { entity: haToggleConfirm.ha_entity_id || haToggleConfirm.name })
        }
        confirmText={t('printers.confirm.haToggleButton')}
        variant={status?.state === 'RUNNING' ? 'danger' : 'default'}
        onConfirm={() => {
          runScriptMutation.mutate({ id: haToggleConfirm.id, action: 'toggle' });
          setHaToggleConfirm(null);
        }}
        onCancel={() => setHaToggleConfirm(null)}
      />
    )}

    {/* Stop Print Confirmation */}
    {showStopConfirm && (
      <ConfirmModal
        title={t('printers.confirm.stopTitle')}
        message={t('printers.confirm.stopMessage', { name: printer.name })}
        confirmText={t('printers.confirm.stopButton')}
        variant="danger"
        onConfirm={() => {
          stopPrintMutation.mutate();
          setShowStopConfirm(false);
        }}
        onCancel={() => setShowStopConfirm(false)}
      />
    )}

    {/* Pause Print Confirmation */}
    {showPauseConfirm && (
      <ConfirmModal
        title={t('printers.confirm.pauseTitle')}
        message={t('printers.confirm.pauseMessage', { name: printer.name })}
        confirmText={t('printers.confirm.pauseButton')}
        variant="default"
        onConfirm={() => {
          pausePrintMutation.mutate();
          setShowPauseConfirm(false);
        }}
        onCancel={() => setShowPauseConfirm(false)}
      />
    )}

    {/* Resume Print Confirmation */}
    {showResumeConfirm && (
      <ConfirmModal
        title={t('printers.confirm.resumeTitle')}
        message={t('printers.confirm.resumeMessage', { name: printer.name })}
        confirmText={t('printers.confirm.resumeButton')}
        variant="default"
        onConfirm={() => {
          resumePrintMutation.mutate();
          setShowResumeConfirm(false);
        }}
        onCancel={() => setShowResumeConfirm(false)}
      />
    )}

    {/* Bed Jog — not-homed warning (Studio-style) */}
    {showNotHomedModal && (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
        <div className="bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded-lg shadow-xl w-full max-w-sm p-5">
          <div className="flex items-start gap-3 mb-4">
            <AlertTriangle className="w-5 h-5 text-yellow-600 dark:text-yellow-400 flex-shrink-0 mt-0.5" />
            <div>
              <h3 className="text-sm font-semibold text-white mb-1">
                {t('printers.bedJog.notHomedTitle')}
              </h3>
              <p className="text-xs text-bambu-gray leading-relaxed">
                {t('printers.bedJog.notHomedMessage')}
              </p>
            </div>
          </div>
          <div className="flex flex-col gap-2">
            <button
              onClick={() => {
                homeAxesMutation.mutate('all');
                setShowNotHomedModal(null);
              }}
              className="w-full px-3 py-2 rounded-lg text-xs font-medium bg-bambu-green/20 text-bambu-green hover:bg-bambu-green/30 transition-colors"
            >
              {t('printers.bedJog.homeZ')}
            </button>
            <button
              onClick={() => {
                const d = showNotHomedModal.distance;
                try { sessionStorage.setItem(`printops.bedJog.warned.${printer.id}`, '1'); } catch { /* ignore */ }
                bedJogMutation.mutate({ distance: d, force: true });
                setShowNotHomedModal(null);
              }}
              className="w-full px-3 py-2 rounded-lg text-xs font-medium bg-yellow-100 dark:bg-yellow-500/20 text-yellow-700 dark:text-yellow-400 hover:bg-yellow-500/30 transition-colors"
            >
              {t('printers.bedJog.moveAnyway')}
            </button>
            <button
              onClick={() => setShowNotHomedModal(null)}
              className="w-full px-3 py-2 rounded-lg text-xs font-medium bg-bambu-dark text-bambu-gray hover:bg-bambu-dark-tertiary transition-colors"
            >
              {t('common.cancel')}
            </button>
          </div>
        </div>
      </div>
    )}

    {/* Skip Objects Modal */}
    <SkipObjectsModal
      printerId={printer.id}
      isOpen={showSkipObjectsModal}
      onClose={() => setShowSkipObjectsModal(false)}
    />

    {/* HMS Error Modal */}
    {showHMSModal && (
      <HMSErrorModal
        printerName={printer.name}
        errors={status?.hms_errors || []}
        onClose={() => setShowHMSModal(false)}
        printerId={printer.id}
        hasPermission={hasPermission}
        runoutGuidance={runoutGuidance}
      />
    )}

    {/* AMS Filament Backup status / control modal (#1762) */}
    {amsBackupModalOpen && status && (
      <AmsBackupModal
        isOpen={amsBackupModalOpen}
        state={status.ams_filament_backup}
        amsUnits={status.ams}
        amsExtruderMap={status.ams_extruder_map}
        isDualNozzle={printer.nozzle_count === 2 || status?.temperatures?.nozzle_2 !== undefined}
        canToggle={canUsePrinterControl}
        pending={setAmsBackupMutation.isPending}
        onToggle={(next) => setAmsBackupMutation.mutate(next)}
        onClose={() => setAmsBackupModalOpen(false)}
      />
    )}

    {/* AMS History Modal */}
    {amsHistoryModal && (
      <AMSHistoryModal
        isOpen={!!amsHistoryModal}
        onClose={() => setAmsHistoryModal(null)}
        printerId={printer.id}
        printerName={printer.name}
        amsId={amsHistoryModal.amsId}
        amsLabel={amsHistoryModal.amsLabel}
        initialMode={amsHistoryModal.mode}
        thresholds={amsThresholds}
      />
    )}

    {/* Heater History Modal (nozzle / bed / chamber) */}
    {heaterHistoryModal && (
      <HeaterHistoryModal
        isOpen={!!heaterHistoryModal}
        onClose={() => setHeaterHistoryModal(null)}
        printerId={printer.id}
        printerName={printer.name}
        initialKind={heaterHistoryModal.initialKind}
        availableKinds={heaterHistoryModal.availableKinds}
      />
    )}

    {/* Link Spool Modal */}
    {linkSpoolModal && (
      <LinkSpoolModal
        isOpen={!!linkSpoolModal}
        onClose={() => setLinkSpoolModal(null)}
        tagUid={linkSpoolModal.tagUid}
        trayUuid={linkSpoolModal.trayUuid}
        printerId={linkSpoolModal.printerId}
        amsId={linkSpoolModal.amsId}
        trayId={linkSpoolModal.trayId}
      />
    )}

    {/* Assign Spool Modal */}
    {assignSpoolModal && (
      <AssignSpoolModal
        isOpen={!!assignSpoolModal}
        onClose={() => setAssignSpoolModal(null)}
        printerId={assignSpoolModal.printerId}
        amsId={assignSpoolModal.amsId}
        trayId={assignSpoolModal.trayId}
        trayInfo={assignSpoolModal.trayInfo}
        spoolmanEnabled={!!spoolmanEnabled}
      />
    )}

    {/* Configure AMS Slot Modal */}
    {configureSlotModal && (
      <ConfigureAmsSlotModal
        isOpen={!!configureSlotModal}
        onClose={() => setConfigureSlotModal(null)}
        printerId={printer.id}
        slotInfo={configureSlotModal}
        printerModel={mapModelCode(printer.model) || undefined}
        onSuccess={() => {
          // Refresh slot presets to show updated profile name
          queryClient.invalidateQueries({ queryKey: ['slotPresets', printer.id] });
          // Printer status will update automatically via WebSocket when AMS data changes
          queryClient.invalidateQueries({ queryKey: ['printerStatus', printer.id] });
        }}
      />
    )}

    {/* Edit Printer Modal */}
    {showEditModal && (
      <EditPrinterModal
        printer={printer}
        onClose={() => setShowEditModal(false)}
      />
    )}

    {/* Firmware Update Modal */}
    {showFirmwareModal && firmwareInfo && (
      <FirmwareUpdateModal
        printer={printer}
        firmwareInfo={firmwareInfo}
        onClose={() => setShowFirmwareModal(false)}
      />
    )}

    {/* AMS Drying Popover — fixed position to avoid overflow/z-index issues */}
    {dryingPopoverAmsId !== null && dryingPopoverPos && (() => {
      const maxTemp = dryingPopoverModuleType === 'n3s' ? 85 : 65;
      const sliderMin = 35;
      const sliderMax = maxTemp + 10;
      return (
        <>
          {/* Backdrop */}
          <div className="fixed inset-0 z-[100]" onClick={() => setDryingPopoverAmsId(null)} />
          {/* Popover */}
          <div
            className="fixed z-[101] flex flex-col w-[240px] bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded-xl shadow-2xl overflow-hidden"
            style={{
              top: dryingPopoverPos.top,
              left: dryingPopoverPos.left,
              // Cap to the space between the popover's top and the bottom
              // viewport margin (8px, matching computePopoverPosition's
              // margin). When the popover is taller than that space — short
              // viewport, landscape phone, zoomed-in — the body scrolls and
              // the footer stays pinned, so the Start button is always
              // reachable (#1458 / #1447 follow-up). dvh (not vh) so iOS
              // Safari's bottom toolbar overlay doesn't clip the footer
              // (#1669, iPhone 17 Safari).
              maxHeight: `calc(100dvh - ${dryingPopoverPos.top}px - 8px)`,
            }}
            onClick={e => e.stopPropagation()}
          >
            {/* Header */}
            <div className="shrink-0 flex items-center justify-center gap-2 px-3 py-2.5">
              <Flame className="w-3.5 h-3.5 text-bambu-green" />
              <span className="text-sm text-white font-medium text-center">{t('printers.drying.start')}</span>
            </div>
            <div className="shrink-0 h-px bg-bambu-dark-tertiary" />
            {/* Body */}
            <div className="px-3 py-2.5 space-y-2.5 overflow-y-auto min-h-0">
              {/* Filament type select */}
              <div>
                <label className="text-[10px] text-white/70 font-medium mb-1 block">{t('printers.filaments')}</label>
                <ToolbarDropdown
                  value={dryingFilament}
                  options={Object.keys(dryingPresets).map(fil => ({ value: fil, label: fil }))}
                  onChange={fil => {
                    setDryingFilament(fil);
                    const preset = dryingPresets[fil];
                    if (preset) {
                      const key = dryingPopoverModuleType === 'n3s' ? 'n3s' : 'n3f';
                      setDryingTemp(preset[key]);
                      setDryingDuration(dryingPopoverModuleType === 'n3s' ? preset.n3s_hours : preset.n3f_hours);
                    }
                  }}
                  fullWidth
                />
              </div>
              {/* Temperature */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-[10px] text-white/70 font-medium">{t('printers.drying.temperature')}</label>
                  <div className="flex items-center gap-1">
                    <NumberField
                      min={45}
                      max={maxTemp}
                      value={dryingTemp}
                      onChange={e => setDryingTemp(Math.min(maxTemp, Math.max(45, Number(e.target.value) || 45)))}
                      className="w-12 px-1 py-0.5 bg-bambu-dark border border-bambu-dark-tertiary rounded text-white text-[11px] text-center focus:outline-none focus:border-bambu-green [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                    />
                    <span className="text-[10px] text-bambu-gray">°C</span>
                  </div>
                </div>
                <Slider
                  min={sliderMin}
                  max={sliderMax}
                  value={dryingTemp}
                  onChange={e => setDryingTemp(Math.min(maxTemp, Math.max(45, Number(e.target.value))))}
                  className="w-full h-1 accent-bambu-green cursor-pointer"
                />
                <div className="flex justify-between text-[9px] text-bambu-gray/50 mt-0.5">
                  <span>45°C</span>
                  <span>{maxTemp}°C</span>
                </div>
              </div>
              {/* Duration */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-[10px] text-white/70 font-medium">{t('printers.drying.duration')}</label>
                  <div className="flex items-center gap-1">
                    <NumberField
                      min={1}
                      max={24}
                      value={dryingDuration}
                      onChange={e => setDryingDuration(Math.min(24, Math.max(1, Number(e.target.value) || 1)))}
                      className="w-10 px-1 py-0.5 bg-bambu-dark border border-bambu-dark-tertiary rounded text-white text-[11px] text-center focus:outline-none focus:border-bambu-green [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                    />
                    <span className="text-[10px] text-bambu-gray">{t('printers.drying.hours')}</span>
                  </div>
                </div>
                <Slider
                  min={1}
                  max={24}
                  value={dryingDuration}
                  onChange={e => setDryingDuration(Number(e.target.value))}
                  className="w-full h-1 accent-bambu-green cursor-pointer"
                />
                <div className="flex justify-between text-[9px] text-bambu-gray/50 mt-0.5">
                  <span>1h</span>
                  <span>24h</span>
                </div>
              </div>
              {/* Rotate tray — disabled when any tray in THIS AMS has its
                  filament threaded out into the feed tube. The whole AMS
                  rotates as one mechanism (all 4 spools turn together), so a
                  single loaded slot locks the entire unit. Bambu per-tray
                  `state`: 9 = empty, 10 = spool present but not loaded
                  (rotation possible), 11 = loaded into tube (rotation impossible).
                  Catches both mid-print (active feed) AND idle-with-threaded-
                  filament — the H2D's post-print state leaves filament in the
                  tube but tray_now resets to 255, which a tray_now-only check
                  would silently miss. */}
              {(() => {
                const targetAms = dryingPopoverAmsId !== null
                  ? amsData.find(a => a.id === dryingPopoverAmsId)
                  : undefined;
                const trayLoadedInThisAms = (targetAms?.tray ?? []).some(
                  tray => tray.state === 11,
                );
                const rotateChecked = dryingRotateTray && !trayLoadedInThisAms;
                return (
                  <div title={trayLoadedInThisAms ? t('printers.drying.rotateUnavailableReason') : undefined}>
                    <button
                      type="button"
                      onClick={() => setDryingRotateTray(enabled => !enabled)}
                      aria-pressed={rotateChecked}
                      aria-disabled={trayLoadedInThisAms}
                      disabled={trayLoadedInThisAms}
                      className={`min-h-10 w-full rounded-lg border px-3 py-1.5 text-[11px] font-medium leading-tight transition-colors ${
                        rotateChecked
                          ? 'bg-bambu-green border-bambu-green text-white'
                          : trayLoadedInThisAms
                            ? 'cursor-not-allowed bg-bambu-dark/80 border-bambu-dark-tertiary text-bambu-gray opacity-60'
                            : 'bg-bambu-dark border-bambu-dark-tertiary text-white hover:bg-bambu-dark-tertiary'
                      }`}
                    >
                      <span className="block whitespace-normal text-center">
                        {t('printers.drying.rotateTray')}
                      </span>
                    </button>
                  </div>
                );
              })()}
            </div>
            <div className="shrink-0 h-px bg-bambu-dark-tertiary" />
            {/* Footer */}
            <div className="shrink-0 px-3 pt-2.5 pb-3">
              <button
                onClick={() => {
                  if (dryingPopoverAmsId !== null) {
                    // Clamp rotateTray off when any tray in this AMS is loaded into
                    // the tube — the rotate UI is disabled there, but the state may
                    // linger as `true` from a previous AMS, or a print may have
                    // started while the popover was open. Without this clamp the
                    // Start payload would carry rotate_tray=true and firmware would
                    // reject with dry_sf_reason=[3] (ConsumableAtAmsOutlet).
                    const targetAms = amsData.find(a => a.id === dryingPopoverAmsId);
                    const trayLoadedInThisAms = (targetAms?.tray ?? []).some(
                      tray => tray.state === 11,
                    );
                    startDryingMutation.mutate({
                      amsId: dryingPopoverAmsId,
                      temp: dryingTemp,
                      duration: dryingDuration,
                      filament: dryingFilament,
                      rotateTray: dryingRotateTray && !trayLoadedInThisAms,
                    });
                  }
                }}
                disabled={startDryingMutation.isPending}
                className="w-full py-1.5 bg-bambu-green hover:bg-bambu-green/80 text-white text-xs font-medium rounded-lg transition-colors disabled:opacity-50"
              >
                {startDryingMutation.isPending ? t('printers.drying.startingDrying') : t('printers.drying.start')}
              </button>
            </div>
          </div>
        </>
      );
    })()}
    </>
  );
}

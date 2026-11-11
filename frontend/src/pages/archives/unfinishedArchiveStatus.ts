export function unfinishedArchiveStatus(status: string) {
  switch (status) {
    case 'failed':
    case 'aborted':
    case 'cancelled':
      return status;
    case 'stopped':
      return 'aborted';
    default:
      return null;
  }
}

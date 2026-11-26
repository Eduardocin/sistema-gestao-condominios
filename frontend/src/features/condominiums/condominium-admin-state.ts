export function canResendRegistration(detailsDirty: boolean, hasStructureDrafts: boolean) {
  return !detailsDirty && !hasStructureDrafts
}

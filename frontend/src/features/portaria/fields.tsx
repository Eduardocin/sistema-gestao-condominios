import { Select } from '../../components'
import { employees, residents, units } from './model'

interface FieldProps { value: string; onChange: (value: string) => void }
const options = (items: { id: string; name: string }[]) => items.map((item) => ({ value: item.id, label: item.name }))
export function EmployeeSelect({ value, onChange }: FieldProps) {
  return <Select label="Funcionário responsável" required value={value} onChange={(event) => onChange(event.target.value)} options={options(employees)} hint="Identifique quem está realizando esta operação." />
}
export function UnitSelect({ value, onChange }: FieldProps) {
  return <Select label="Unidade de destino" required value={value} onChange={(event) => onChange(event.target.value)} options={options(units)} />
}
export function ResidentSelect({ value, onChange, unitId, label = 'Destinatário' }: FieldProps & { unitId: string; label?: string }) {
  return <Select label={label} required value={value} onChange={(event) => onChange(event.target.value)} disabled={!unitId} options={options(residents.filter((resident) => resident.unitId === unitId))} hint="Somente moradores com vínculo ativo na unidade." />
}

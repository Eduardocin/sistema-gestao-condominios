import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import { Badge, Button, Card, Heading, Input, Notice, RecordPhoto, Text, Upload } from '../../components'
import { EmployeeSelect, ResidentSelect, UnitSelect } from './fields'
import { receivePackage } from './model'
import type { Parcel } from './model'
import { useContentFocus } from './useContentFocus'
import styles from './Portaria.module.css'

export function ReceiptForm({ onSave, onCancel }: { onSave: (parcel: Parcel) => void; onCancel: () => void }) {
  const [unitId, setUnitId] = useState('')
  const [residentId, setResidentId] = useState('')
  const [employeeId, setEmployeeId] = useState('')
  const [description, setDescription] = useState('')
  const [photo, setPhoto] = useState('')
  const [error, setError] = useState('')
  const [photoError, setPhotoError] = useState('')
  const [reading, setReading] = useState(false)
  const requestId = useRef(0)
  useContentFocus('receipt-title')
  useEffect(() => () => { requestId.current += 1 }, [])

  async function selectPhoto(event: ChangeEvent<HTMLInputElement>) {
    const currentRequest = ++requestId.current
    const file = event.target.files?.[0]
    setPhoto('')
    setError('')
    setPhotoError('')
    setReading(false)
    if (!file) return
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024) {
      setPhotoError('Selecione uma imagem JPG, PNG ou WebP de até 5 MB. Os outros campos foram mantidos.')
      return
    }
    setReading(true)
    try {
      const data = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader()
        reader.onerror = () => reject(new Error('Falha ao ler a foto'))
        reader.onload = () => resolve(String(reader.result))
        reader.readAsDataURL(file)
      })
      const image = new Image()
      image.src = data
      await image.decode()
      if (currentRequest === requestId.current) setPhoto(data)
    } catch {
      if (currentRequest === requestId.current) setPhotoError('Não foi possível abrir a foto. Tente outro arquivo; os dados preenchidos foram mantidos.')
    } finally {
      if (currentRequest === requestId.current) setReading(false)
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    if (reading) return
    if (!photo) setPhotoError('Anexe uma foto antes de confirmar o recebimento.')
    const result = receivePackage({ unitId, residentId, employeeId, description, photo }, new Date().toISOString())
    if (!result.ok) { setError(result.error); return }
    onSave(result.value)
  }

  return <section className={styles.stack} aria-labelledby="receipt-title">
    <div className={styles.headingRow}><div><Text size="sm" tone="secondary">FLUXO 01 · RECEBIMENTO</Text><Heading level={1} id="receipt-title" tabIndex={-1}>Receber encomenda</Heading><Text tone="secondary">Registre o que chegou e para quem deve ser entregue.</Text></div><Button variant="secondary" onClick={onCancel}>Voltar às encomendas</Button></div>
    <form onSubmit={submit} className={styles.formLayout}>
      <Card className={styles.stack}>
        <Heading level={2} size="md">Dados do recebimento</Heading>
        <div className={styles.twoColumns}><UnitSelect value={unitId} onChange={(value) => { setUnitId(value); setResidentId('') }} /><ResidentSelect value={residentId} onChange={setResidentId} unitId={unitId} /></div>
        <Input label="Descrição da encomenda" placeholder="Ex.: caixa pequena, envelope ou nome da loja" required maxLength={200} value={description} onChange={(event) => setDescription(event.target.value)} />
        <EmployeeSelect value={employeeId} onChange={setEmployeeId} />
        <Heading level={2} size="md">Foto da encomenda <Badge variant="warning">Obrigatória</Badge></Heading>
        <Text size="sm" tone="secondary" id="photo-hint">Fotografe ou selecione uma imagem JPG, PNG ou WebP de até 5 MB. Nesta prévia, a foto não é enviada.</Text>
        <Upload label="Selecionar foto da encomenda" accept="image/jpeg,image/png,image/webp" onChange={selectPhoto} aria-describedby="photo-hint photo-error" aria-invalid={Boolean(photoError) || undefined} />
        <div id="photo-error" aria-live="polite">{photoError && <Notice tone="alert">{photoError}</Notice>}</div>
        {reading && <Text role="status">Preparando a foto…</Text>}
        {photo && <RecordPhoto src={photo} alt="Prévia da foto da encomenda" />}
        {error && <Notice tone="alert" role="alert">{error}</Notice>}
        <div className={styles.actions}><Button variant="secondary" onClick={onCancel}>Cancelar</Button><Button type="submit" loading={reading}>Confirmar recebimento</Button></div>
      </Card>
      <div className={styles.stack}><Card className={styles.stack}><Badge variant="primary">O próximo passo</Badge><Heading level={2} size="md">Pronta para retirar</Heading><Text size="sm" tone="secondary">Após o registro, a encomenda fica disponível na lista com o status:</Text><Badge variant="warning">Aguardando retirada</Badge><Text size="sm" tone="secondary">A data, a hora e o funcionário responsável ficam registrados no histórico.</Text></Card><Notice>A entrega e a confirmação do morador acontecem em etapas separadas.</Notice></div>
    </form>
  </section>
}

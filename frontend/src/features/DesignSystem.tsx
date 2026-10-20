import React, { useState } from 'react';
import { Button } from '../components/Button';
import { Input } from '../components/Input';
import { Badge } from '../components/Badge';
import { Table } from '../components/Table';
import { Card } from '../components/Card';
import { Select } from '../components/Select';
import { Modal } from '../components/Modal';
import { Toast } from '../components/Toast';
import { Upload } from '../components/Upload';
import { TimeGrid, type TimeSlotData } from '../components/TimeGrid';

export const DesignSystem: React.FC = () => {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isToastVisible, setIsToastVisible] = useState(false);

  // Dados fictícios para testar a Grade de Horários
  const mockTimeSlots: TimeSlotData[] = [
    { time: '08:00', status: 'other' },
    { time: '09:00', status: 'other' },
    { time: '10:00', status: 'free' },
    { time: '11:00', status: 'free' },
    { time: '12:00', status: 'free' },
    { time: '13:00', status: 'own' },
    { time: '14:00', status: 'own' },
    { time: '15:00', status: 'free' },
    { time: '16:00', status: 'other' },
  ];

  return (
    <div style={{ padding: '40px', fontFamily: 'sans-serif' }}>
      <h1>Design System - Condomínio</h1>
      <hr style={{ margin: '20px 0' }} />

      <h2>1. Botões</h2>
      <div style={{ display: 'flex', gap: '10px', marginBottom: '30px' }}>
        <Button variant="primary">Ação Principal</Button>
        <Button variant="success">Salvar</Button>
        <Button variant="alert">Excluir</Button>
        <Button variant="warning">Atenção</Button>
      </div>

      <h2>2. Campos de Texto (Inputs)</h2>
      <div style={{ maxWidth: '300px', marginBottom: '30px' }}>
        <Input id="email" label="E-mail" placeholder="Digite o e-mail" type="email" />
        <Input id="senha" label="Palavra-passe" placeholder="********" type="password" />
      </div>

      <h2>3. Badges (Etiquetas de Status)</h2>
      <div style={{ display: 'flex', gap: '10px', marginBottom: '30px' }}>
        <Badge variant="success">Resolvida</Badge>
        <Badge variant="alert">Em Aberto</Badge>
        <Badge variant="warning">Pendente</Badge>
      </div>

      <h2>4. Tabela</h2>
      <div style={{ marginBottom: '40px' }}>
        <Table 
          headers={['Morador', 'Unidade', 'Status da Ocorrência', 'Ação']}
          rows={[
            ['Matheus Sobreira', '101', <Badge variant="success">Resolvida</Badge>, <Button variant="primary">Ver</Button>],
            ['Ana Clara', '204', <Badge variant="alert">Em Aberto</Badge>, <Button variant="primary">Ver</Button>]
          ]}
        />
      </div>

      <h2>5. Cartão (Card) e Select</h2>
      <div style={{ maxWidth: '400px', marginBottom: '40px' }}>
        <Card>
          <h3 style={{ marginTop: 0 }}>Formulário de Registo</h3>
          <p style={{ color: 'var(--color-text-secondary)', fontSize: '14px', marginBottom: '20px' }}>
            Preencha os dados da encomenda.
          </p>
          <Select 
            id="unidade" 
            label="Unidade de Destino" 
            options={[
              { value: '101', label: 'Apartamento 101' },
              { value: '102', label: 'Apartamento 102' }
            ]} 
          />
        </Card>
      </div>

      <h2>6. Modal (Janela Flutuante)</h2>
      <div style={{ marginBottom: '40px' }}>
        <Button variant="primary" onClick={() => setIsModalOpen(true)}>
          Abrir Modal de Teste
        </Button>
        <Modal title="Confirmar Exclusão" isOpen={isModalOpen} onClose={() => setIsModalOpen(false)}>
          <p style={{ color: 'var(--color-text-secondary)', marginBottom: '24px', lineHeight: '1.5' }}>
            Tem a certeza de que deseja excluir o registo deste visitante?
          </p>
          <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
            <Button variant="primary" onClick={() => setIsModalOpen(false)}>Cancelar</Button>
            <Button variant="alert" onClick={() => setIsModalOpen(false)}>Sim, Excluir</Button>
          </div>
        </Modal>
      </div>

      <h2>7. Aviso (Toast)</h2>
      <div style={{ marginBottom: '40px' }}>
        <Button variant="success" onClick={() => setIsToastVisible(true)}>
          Disparar Aviso de Sucesso
        </Button>
        <Toast 
          message="Encomenda registada com sucesso!" 
          variant="success"
          isVisible={isToastVisible} 
          onClose={() => setIsToastVisible(false)} 
        />
      </div>

      <h2>8. Upload de Ficheiros</h2>
      <div style={{ maxWidth: '400px', marginBottom: '40px' }}>
        <Upload id="nota-fiscal" label="Anexar Arquivo" accept="image/png, image/jpeg" />
      </div>

      <h2>9. Calendário e Grade de Horários</h2>
      <div style={{ maxWidth: '500px', marginBottom: '40px' }}>
        <Card>
          {/* Usamos o nosso Input como um seletor nativo de data do navegador */}
          <Input id="data-reserva" label="Data da Reserva" type="date" />
          
          <div style={{ marginTop: '24px' }}>
            <label className="input-label">Horários da Quadra Polidesportiva</label>
            <TimeGrid 
              slots={mockTimeSlots} 
              onSlotClick={(time, status) => {
                if(status === 'free') alert(`Iniciando reserva para as ${time}`);
                else if(status === 'other') alert(`Horário ${time} indisponível.`);
              }} 
            />
          </div>
        </Card>
      </div>

    </div>
  );
};
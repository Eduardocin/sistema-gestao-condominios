# Design System

Guia para montar telas do frontend usando só as peças do design system, sem criar estilo próprio.

Veja tudo funcionando em <http://127.0.0.1:5173/design-system> (com o frontend rodando).

## Como usar

```tsx
import { Button, Card, Heading, Input, Page, Table } from '../../components'

export function MinhaTela() {
  return (
    <Page>
      <Heading level={1}>Encomendas</Heading>
      <Card>
        <Input label="Unidade" hint="Ex.: 101" />
        <Button variant="success">Registrar</Button>
      </Card>
    </Page>
  )
}
```

Importe sempre de `components` (arquivo `index.ts`), nunca de um arquivo específico.

## Regras

1. **Sem cores, tamanhos ou espaços soltos.** Nada de `#0f52ba`, `16px` ou `style={{ ... }}` para aparência. Use as variáveis de `src/styles/tokens.css` (`var(--color-primary)`, `var(--space-4)`).
2. **Estilo de tela vai num CSS Module** (`MinhaTela.module.css`) e só para layout (grade, alinhamento, espaçamento entre blocos). Aparência de botão, campo, tabela etc. vem do componente.
3. **Precisa de algo que não existe?** Crie o componente em `src/components`, com CSS Module próprio, e adicione na página `/design-system` com seus estados.
4. **Todo campo tem rótulo** (`label` é obrigatório em `Input` e `Select`) e todo erro é escrito em texto.
5. **Status nunca só por cor.** Badge e TimeGrid já trazem texto; mantenha isso em componentes novos.

## Tokens

| Grupo | Variáveis |
|---|---|
| Cores | `--color-primary` (Azul Safira), `--color-success*`, `--color-alert*`, `--color-warning*`, `--color-text-*`, `--color-border*` |
| Tipografia | `--font-size-xs` a `--font-size-3xl`, `--font-weight-*`, `--line-height-*` |
| Espaçamento | `--space-1` (4px) a `--space-7` (48px) |
| Raios e sombras | `--radius-sm/md/lg/pill`, `--shadow-sm/md/lg` |

Para cada status há quatro tons: base (destaque), `-strong` (fundo sólido com texto branco), `-soft` (fundo suave) e `-text` (texto sobre o fundo suave). Os pares foram escolhidos para atingir contraste mínimo de 4,5:1.

## Componentes

`Button`, `Input`, `Select`, `Table`, `Card`, `Modal`, `Badge`, `Calendar`, `TimeGrid`, `Upload`, `Toast`, mais `Page`, `Heading`, `Text` e `VisuallyHidden`.

## Acessibilidade já embutida

- Foco visível por teclado em todos os controles.
- `Modal` usa `<dialog>` nativo: prende o foco, fecha com Esc e devolve o foco ao botão que o abriu.
- `Toast` anuncia a mensagem para leitores de tela e some sozinho em 6 s (`duration={0}` desliga).
- `Calendar` navega com setas, Home, End, PageUp e PageDown.
- `TimeGrid` e `Upload` funcionam só com o teclado.

import { useEffect, useRef } from 'react'
import type { PointerEvent } from 'react'
import { Link } from 'react-router'
import { Badge, ButtonLink } from '../../components'
import { HomeIcon } from './HomeIcon'
import { HomePreview } from './HomePreview'
import styles from './HomePage.module.css'

function highlightCard(event: PointerEvent<HTMLElement>) {
  if (
    event.pointerType === 'touch' ||
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
    return
  const card = event.currentTarget
  const bounds = card.getBoundingClientRect()
  card.style.setProperty('--pointer-x', `${event.clientX - bounds.left}px`)
  card.style.setProperty('--pointer-y', `${event.clientY - bounds.top}px`)
}

export function HomePage() {
  const page = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const root = page.current
    if (!root || !('IntersectionObserver' in window)) return

    const motion = window.matchMedia('(prefers-reduced-motion: reduce)')
    const elements = Array.from(root.querySelectorAll<HTMLElement>(`.${styles.reveal}`))
    const pending = new Set<HTMLElement>()
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach(({ isIntersecting, target }) => {
          if (!isIntersecting) return
          target.classList.remove(styles.pending)
          pending.delete(target as HTMLElement)
          observer.unobserve(target)
        })
      },
      { threshold: 0.12 },
    )

    function syncMotion() {
      if (motion.matches) {
        observer.disconnect()
        pending.forEach((element) => element.classList.remove(styles.pending))
        pending.clear()
        return
      }

      elements.forEach((element) => {
        if (element.getBoundingClientRect().top < window.innerHeight || pending.has(element)) return
        pending.add(element)
        element.classList.add(styles.pending)
        observer.observe(element)
      })
    }

    syncMotion()
    motion.addEventListener('change', syncMotion)
    return () => {
      motion.removeEventListener('change', syncMotion)
      observer.disconnect()
      pending.forEach((element) => element.classList.remove(styles.pending))
    }
  }, [])

  return (
    <div ref={page} className={styles.landing}>
      <a className={styles.skipLink} href="#conteudo">
        Pular para o conteúdo
      </a>
      <header className={styles.topbar}>
        <div className={styles.wrap + ' ' + styles.nav}>
          <a className={styles.brand} href="#conteudo" aria-label="Gestão de Condomínios, início">
            <span className={styles.brandMark}>
              <HomeIcon name="building" />
            </span>
            <span>Gestão de Condomínios</span>
          </a>
          <nav className={styles.navLinks} aria-label="Navegação principal">
            <a href="#recursos">Recursos</a>
            <a href="#para-quem">Para quem</a>
            <a href="#como-funciona">Como funciona</a>
          </nav>
          <ButtonLink
            to="/login"
            variant="secondary"
            size="sm"
            className={styles.button + ' ' + styles.ghost + ' ' + styles.sm}
          >
            Entrar
          </ButtonLink>
        </div>
      </header>

      <main id="conteudo" tabIndex={-1}>
        <div className={styles.heroBg}>
          <section className={styles.wrap + ' ' + styles.hero} aria-labelledby="hero-title">
            <div className={styles.heroCopy}>
              <Badge variant="primary" className={styles.badge}>
                <span className={styles.dot}>
                  <HomeIcon name="spark" />
                </span>
                Gestão que aproxima
              </Badge>
              <h1 id="hero-title">
                A vida em condomínio, <span className={styles.gradientText}>mais simples</span> para
                todos.
              </h1>
              <p className={styles.lead}>
                Moradores, administração e portaria conectados em uma plataforma feita para
                organizar as rotinas e dar mais clareza ao dia a dia.
              </p>
              <div className={styles.actions}>
                <ButtonLink to="/cadastro" className={styles.button}>
                  Criar minha conta
                  <HomeIcon name="arrow" />
                </ButtonLink>
                <a className={styles.button + ' ' + styles.ghost} href="#recursos">
                  Conhecer a plataforma
                </a>
              </div>
              <ul className={styles.checks}>
                <li>
                  <HomeIcon name="check" />
                  Tudo em um só lugar
                </li>
                <li>
                  <HomeIcon name="check" />
                  Dados isolados por condomínio
                </li>
              </ul>
            </div>

            <HomePreview />
          </section>
        </div>

        <section id="recursos" className={styles.section} aria-labelledby="recursos-titulo">
          <div id="funcionalidades" className={styles.wrap}>
            <div className={styles.sectionHead + ' ' + styles.reveal}>
              <span className={styles.eyebrow}>Um só lugar para o essencial</span>
              <h2 id="recursos-titulo">Mais organização em cada rotina.</h2>
              <p>
                Ferramentas que ajudam a acompanhar o que acontece no condomínio com menos
                desencontro de informação.
              </p>
            </div>
            <div className={styles.bento}>
              <article
                onPointerMove={highlightCard}
                className={styles.card + ' ' + styles.c3 + ' ' + styles.reveal}
              >
                <span className={styles.cardIcon}>
                  <HomeIcon name="box" />
                </span>
                <h3>Encomendas</h3>
                <p>
                  Registro na portaria, com foto, e acompanhamento até a confirmação de retirada
                  pelo morador.
                </p>
                <div className={styles.flow}>
                  <span className={styles.chip}>Aguardando retirada</span>
                  <HomeIcon name="arrow" className={styles.arrow} />
                  <span className={styles.chip}>Entregue</span>
                  <HomeIcon name="arrow" className={styles.arrow} />
                  <span className={styles.chip + ' ' + styles.on}>Retirada confirmada</span>
                </div>
              </article>
              <article
                onPointerMove={highlightCard}
                className={styles.card + ' ' + styles.c3 + ' ' + styles.reveal}
              >
                <span className={styles.cardIcon}>
                  <HomeIcon name="people" />
                </span>
                <h3>Visitantes</h3>
                <p>
                  Autorizações feitas pelo morador e registros de entrada e saída pela portaria, em
                  um fluxo claro.
                </p>
                <div className={styles.flow}>
                  <span className={styles.chip}>Autorizada</span>
                  <HomeIcon name="arrow" className={styles.arrow} />
                  <span className={styles.chip}>Entrou</span>
                  <HomeIcon name="arrow" className={styles.arrow} />
                  <span className={styles.chip + ' ' + styles.on}>Saiu</span>
                </div>
              </article>
              <article
                onPointerMove={highlightCard}
                className={styles.card + ' ' + styles.c2 + ' ' + styles.reveal}
              >
                <span className={styles.cardIcon}>
                  <HomeIcon name="calendar" />
                </span>
                <h3>Reservas</h3>
                <p>Consulte espaços comuns e acompanhe as reservas da unidade.</p>
              </article>
              <article
                onPointerMove={highlightCard}
                className={styles.card + ' ' + styles.c2 + ' ' + styles.reveal}
              >
                <span className={styles.cardIcon}>
                  <HomeIcon name="chat" />
                </span>
                <h3>Ocorrências</h3>
                <p>Registre solicitações e acompanhe o andamento junto à administração.</p>
              </article>
              <article
                onPointerMove={highlightCard}
                className={styles.card + ' ' + styles.c2 + ' ' + styles.reveal}
              >
                <span className={styles.cardIcon}>
                  <HomeIcon name="bell" />
                </span>
                <h3>Avisos</h3>
                <p>Comunicados com período de vigência, para manter a comunidade informada.</p>
              </article>
              <article
                onPointerMove={highlightCard}
                className={styles.card + ' ' + styles.c6 + ' ' + styles.reveal}
              >
                <span className={styles.cardIcon}>
                  <HomeIcon name="building" />
                </span>
                <div className={styles.c6Copy}>
                  <h3>Condomínio conectado</h3>
                  <p>
                    Pessoas, unidades e responsabilidades reunidas na mesma plataforma, com cada
                    condomínio isolado dos demais.
                  </p>
                </div>
                <div
                  className={styles.flow + ' ' + styles.c6Tags}
                  aria-label="O que a plataforma conecta"
                >
                  <span className={styles.chip}>Pessoas</span>
                  <span className={styles.chip}>Unidades</span>
                  <span className={styles.chip}>Responsáveis</span>
                  <span className={styles.chip + ' ' + styles.on}>Dados isolados</span>
                </div>
              </article>
            </div>
          </div>
        </section>

        <section id="para-quem" className={styles.section}>
          <div className={styles.wrap + ' ' + styles.roles}>
            <div className={styles.rolesCopy + ' ' + styles.reveal}>
              <span className={styles.eyebrow}>Uma experiência para cada papel</span>
              <h2>Todo mundo sabe onde encontrar o que precisa.</h2>
              <p>
                As informações certas para cada pessoa, com uma experiência pensada para as
                diferentes responsabilidades do condomínio.
              </p>
            </div>
            <div className={styles.roleList}>
              <article className={styles.role + ' ' + styles.reveal}>
                <span className={styles.roleIc}>
                  <HomeIcon name="people" />
                </span>
                <div>
                  <h3>Moradores</h3>
                  <p>Acompanham encomendas, autorizam visitas e participam da rotina.</p>
                </div>
              </article>
              <article className={styles.role + ' ' + styles.reveal}>
                <span className={styles.roleIc}>
                  <HomeIcon name="building" />
                </span>
                <div>
                  <h3>Administração</h3>
                  <p>Organiza avisos, unidades, solicitações e áreas comuns.</p>
                </div>
              </article>
              <article className={styles.role + ' ' + styles.reveal}>
                <span className={styles.roleIc}>
                  <HomeIcon name="key" />
                </span>
                <div>
                  <h3>Portaria</h3>
                  <p>Registra encomendas e movimentações de visitantes com clareza.</p>
                </div>
              </article>
            </div>
          </div>
        </section>

        <section id="como-funciona" className={styles.section + ' ' + styles.how}>
          <div className={styles.wrap}>
            <div className={styles.sectionHead + ' ' + styles.reveal}>
              <span className={styles.eyebrow}>Comece com clareza</span>
              <h2>Uma rotina conectada, passo a passo.</h2>
              <p>
                Um caminho simples para estruturar as informações e colocar cada pessoa em seu
                espaço.
              </p>
            </div>
            <ol className={styles.steps}>
              <li className={styles.step + ' ' + styles.reveal}>
                <div className={styles.stepBody}>
                  <h3>Cadastre o condomínio</h3>
                  <p>
                    A administração informa os dados necessários e acompanha a análise do cadastro.
                  </p>
                </div>
              </li>
              <li className={styles.step + ' ' + styles.reveal}>
                <div className={styles.stepBody}>
                  <h3>Conecte as pessoas</h3>
                  <p>Organize unidades e vínculos de moradores e funcionários.</p>
                </div>
              </li>
              <li className={styles.step + ' ' + styles.reveal}>
                <div className={styles.stepBody}>
                  <h3>Acompanhe o dia a dia</h3>
                  <p>Use os fluxos de encomendas, visitas, reservas e solicitações.</p>
                </div>
              </li>
            </ol>
          </div>
        </section>

        <section className={styles.closing}>
          <div className={styles.wrap}>
            <div className={styles.closingCard + ' ' + styles.reveal}>
              <div>
                <h2>Mais clareza para cuidar do que é de todos.</h2>
                <p>Conheça uma forma mais organizada de viver a rotina em condomínio.</p>
              </div>
              <ButtonLink to="/cadastro" className={styles.button}>
                Criar minha conta
                <HomeIcon name="arrow" />
              </ButtonLink>
            </div>
          </div>
        </section>
      </main>

      <footer>
        <div className={styles.wrap + ' ' + styles.footerRow}>
          <a className={styles.brand} href="#conteudo">
            <span className={styles.brandMark}>
              <HomeIcon name="building" />
            </span>
            <span>Gestão de Condomínios</span>
          </a>
          <p>Tecnologia para uma rotina mais próxima.</p>
          <nav className={styles.footerLinks} aria-label="Links do rodapé">
            <Link to="/login">Entrar</Link>
            <Link to="/cadastro">Criar conta</Link>
          </nav>
        </div>
      </footer>
    </div>
  )
}

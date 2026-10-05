import { FormEvent, useEffect, useState, type ReactNode } from "react";
import { listarExemplos, perguntar, type Dados, type Resposta } from "./api";

type Turno = { pergunta: string; resposta?: Resposta; erro?: string };

export function App() {
  const [exemplos, setExemplos] = useState<string[]>([]);
  const [texto, setTexto] = useState("");
  const [turnos, setTurnos] = useState<Turno[]>([]);
  const [conversaId, setConversaId] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    listarExemplos()
      .then(setExemplos)
      .catch(() => setExemplos([]));
  }, []);

  async function enviar(pergunta: string) {
    const frase = pergunta.trim();
    if (!frase || enviando) return;
    setTexto("");
    setEnviando(true);
    setTurnos((atuais) => [...atuais, { pergunta: frase }]);
    try {
      const resposta = await perguntar(frase, conversaId);
      setConversaId(resposta.conversa_id);
      setTurnos((atuais) => atuais.map((turno, indice) => (indice === atuais.length - 1 ? { ...turno, resposta } : turno)));
    } catch (erro) {
      const mensagem = erro instanceof Error ? erro.message : "Falha ao perguntar.";
      setTurnos((atuais) => atuais.map((turno, indice) => (indice === atuais.length - 1 ? { ...turno, erro: mensagem } : turno)));
    } finally {
      setEnviando(false);
    }
  }

  function aoEnviar(evento: FormEvent) {
    evento.preventDefault();
    void enviar(texto);
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar-inner">
          <span className="brand">
            <span className="brand-mark" aria-hidden="true">
              <span />
              <span />
              <span />
            </span>
            CineData
          </span>
          <span className="topbar-divider" />
          <h1>Pergunte ao catálogo</h1>
        </div>
      </header>

      <main className="conversation">
        {turnos.length === 0 && (
          <section className="exemplos">
            <p>Escolha uma pergunta ou escreva a sua.</p>
            <div className="chips">
              {exemplos.map((exemplo) => (
                <button key={exemplo} type="button" onClick={() => void enviar(exemplo)} disabled={enviando}>
                  {exemplo}
                </button>
              ))}
            </div>
          </section>
        )}
        {turnos.map((turno, indice) => (
          <article key={`${indice}-${turno.pergunta}`} className="turno">
            <section className="message user-message" aria-label="Pergunta do usuário">
              <span className="message-label">Você</span>
              <p>{turno.pergunta}</p>
            </section>
            {turno.erro && <p className="erro">{turno.erro}</p>}
            {turno.resposta && <RespostaPainel resposta={turno.resposta} />}
            {!turno.resposta && !turno.erro && <p className="aguardando">Consultando o catálogo…</p>}
          </article>
        ))}
      </main>

      <footer className="composer-dock">
        <form className="composer" onSubmit={aoEnviar}>
          <label className="sr-only" htmlFor="query">
            Faça uma pergunta sobre o catálogo
          </label>
          <input
            id="query"
            value={texto}
            onChange={(evento) => setTexto(evento.target.value)}
            placeholder="Ex.: Top 10 filmes com maior receita em R$"
            disabled={enviando}
          />
          <button type="submit" disabled={enviando || !texto.trim()}>
            Perguntar
            <svg aria-hidden="true" viewBox="0 0 20 20">
              <path d="M4 10h11M11 6l4 4-4 4" />
            </svg>
          </button>
        </form>
        <p>As respostas são calculadas a partir dos dados do catálogo.</p>
      </footer>
    </div>
  );
}

function RespostaPainel({ resposta }: { resposta: Resposta }) {
  const [calculoAberto, setCalculoAberto] = useState(false);
  const [sqlAberto, setSqlAberto] = useState(false);
  const temBarras = resposta.visualizacao?.tipo === "barra" && Boolean(resposta.dados);

  return (
    <section className="message answer-message" aria-label="Resposta do CineData">
      <div className="answer-heading">
        <span className="answer-mark" aria-hidden="true">
          C
        </span>
        <span>CineData</span>
      </div>
      <p className="answer-copy">{resposta.resposta}</p>
      {temBarras && resposta.dados && <Barras dados={resposta.dados} eixos={resposta.visualizacao?.eixos ?? []} />}
      {resposta.dados && <Tabela dados={resposta.dados} />}
      <div className="details">
        {resposta.explicacao && (
          <Detail title="Como cheguei nesse número" open={calculoAberto} onToggle={() => setCalculoAberto((atual) => !atual)}>
            <p>{resposta.explicacao}</p>
          </Detail>
        )}
        {resposta.sql && (
          <Detail title="SQL" open={sqlAberto} onToggle={() => setSqlAberto((atual) => !atual)}>
            <div className="code-wrap">
              <pre>
                <code>{resposta.sql}</code>
              </pre>
            </div>
          </Detail>
        )}
      </div>
    </section>
  );
}

function Detail({
  title,
  open,
  onToggle,
  children,
}: {
  title: string;
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <section className={`detail ${open ? "detail-open" : ""}`}>
      <button aria-expanded={open} className="detail-trigger" onClick={onToggle} type="button">
        <span>{title}</span>
        <Chevron open={open} />
      </button>
      {open && <div className="detail-content">{children}</div>}
    </section>
  );
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg aria-hidden="true" className={`chevron ${open ? "chevron-open" : ""}`} viewBox="0 0 20 20">
      <path d="m7.5 5 5 5-5 5" />
    </svg>
  );
}

function Tabela({ dados }: { dados: Dados }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {dados.colunas.map((coluna) => (
              <th key={coluna}>{coluna}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {dados.linhas.map((linha, indice) => (
            <tr key={indice}>
              {linha.map((celula, coluna) => (
                <td key={coluna}>{formatarCelula(celula)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {dados.truncado && <p className="aviso">Resultado truncado pelo teto de linhas.</p>}
    </div>
  );
}

function Barras({ dados, eixos }: { dados: Dados; eixos: string[] }) {
  const indiceRotulo = Math.max(0, dados.colunas.indexOf(eixos[0] ?? dados.colunas[0]));
  const indiceValor = dados.colunas.indexOf(eixos[1] ?? "");
  const valorColuna = indiceValor >= 0 ? indiceValor : dados.colunas.findIndex((_, indice) => typeof dados.linhas[0]?.[indice] === "number");
  if (valorColuna < 0) return null;
  const pontos = dados.linhas.slice(0, 10).map((linha) => ({
    rotulo: String(linha[indiceRotulo] ?? ""),
    valor: Number(linha[valorColuna] ?? 0),
  }));
  const maior = Math.max(...pontos.map((ponto) => Math.abs(ponto.valor)), 1);
  return (
    <div className="barras">
      {pontos.map((ponto) => (
        <div key={ponto.rotulo} className="item-barra">
          <span>{ponto.rotulo}</span>
          <div>
            <i style={{ width: `${(Math.abs(ponto.valor) / maior) * 100}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}

function formatarCelula(celula: Dados["linhas"][number][number]): string {
  if (celula == null) return "—";
  if (typeof celula === "number") {
    return Number.isInteger(celula)
      ? celula.toLocaleString("pt-BR")
      : celula.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  return String(celula);
}

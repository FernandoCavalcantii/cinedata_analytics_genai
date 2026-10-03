import { FormEvent, useEffect, useState } from "react";
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
    <div className="shell">
      <header className="topo">
        <p className="marca">CineData</p>
        <h1>Pergunte ao catálogo</h1>
      </header>
      <main className="conversa">
        {turnos.length === 0 && (
          <section className="exemplos">
            <p>Escolha uma pergunta do edital ou escreva a sua.</p>
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
            <p className="pergunta">{turno.pergunta}</p>
            {turno.erro && <p className="erro">{turno.erro}</p>}
            {turno.resposta && <RespostaPainel resposta={turno.resposta} />}
            {!turno.resposta && !turno.erro && <p className="aguardando">Consultando o catálogo…</p>}
          </article>
        ))}
      </main>
      <form className="barra" onSubmit={aoEnviar}>
        <input
          value={texto}
          onChange={(evento) => setTexto(evento.target.value)}
          placeholder="Ex.: Top 10 filmes com maior receita em R$"
          aria-label="Pergunta"
        />
        <button type="submit" disabled={enviando || !texto.trim()}>
          Perguntar
        </button>
      </form>
    </div>
  );
}

function RespostaPainel({ resposta }: { resposta: Resposta }) {
  return (
    <div className={`painel status-${resposta.status}`}>
      <p className="texto">{resposta.resposta}</p>
      {resposta.explicacao && <p className="explicacao">{resposta.explicacao}</p>}
      {resposta.visualizacao?.tipo === "barra" && resposta.dados && (
        <Barras dados={resposta.dados} eixos={resposta.visualizacao.eixos ?? []} />
      )}
      {resposta.dados && <Tabela dados={resposta.dados} />}
      <footer>
        <span>{resposta.metadados.modelo || "sem modelo"}</span>
        <span>{resposta.metadados.requisicoes} req</span>
        <span>{resposta.metadados.cache ? "cache" : `${resposta.metadados.tempo_ms} ms`}</span>
      </footer>
      {resposta.sql && <pre>{resposta.sql}</pre>}
    </div>
  );
}

function Tabela({ dados }: { dados: Dados }) {
  return (
    <div className="tabela-wrap">
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
                <td key={coluna}>{celula == null ? "—" : String(celula)}</td>
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

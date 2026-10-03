import type { components } from "./schema";

const BASE = import.meta.env.VITE_API_URL ?? "";

export type Resposta = components["schemas"]["RespostaServico"];
export type Dados = components["schemas"]["DadosResposta"];

export async function listarExemplos(): Promise<string[]> {
  const resposta = await fetch(`${BASE}/api/v1/exemplos`);
  if (!resposta.ok) throw new Error("Não foi possível carregar os exemplos.");
  const corpo = (await resposta.json()) as components["schemas"]["ListaExemplos"];
  return corpo.perguntas;
}

export async function perguntar(pergunta: string, conversaId: string | null): Promise<Resposta> {
  const pedido: components["schemas"]["PedidoPergunta"] = { pergunta, conversa_id: conversaId };
  const resposta = await fetch(`${BASE}/api/v1/perguntas`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(pedido),
  });
  if (!resposta.ok) {
    const corpo = (await resposta.json()) as components["schemas"]["ErroAPI"];
    throw new Error(corpo.erro ?? "A API não respondeu.");
  }
  return (await resposta.json()) as Resposta;
}

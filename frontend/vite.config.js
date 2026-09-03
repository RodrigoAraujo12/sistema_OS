import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/**
 * Rotas de raiz do backend (ver backend/main.py). O proxy precisa saber
 * o que e chamada de API e o que e rota da SPA — todo o resto e servido
 * como pagina.
 */
const ROTAS_API = [
  "/auth",
  "/ordens",
  "/alertas",
  "/admin",
  "/equipes-fiscais",
  "/relatorios",
  "/docs",
  "/openapi.json",
];

const proxy = Object.fromEntries(
  ROTAS_API.map((rota) => [
    rota,
    { target: "http://127.0.0.1:8000", changeOrigin: true },
  ]),
);

// host: true publica na rede (0.0.0.0); porta 5000 e a unica liberada no
// firewall. O backend continua preso em 127.0.0.1 e so e alcancado por
// este proxy: assim uma unica porta sai da maquina e a API nao fica
// exposta por conta propria. Como front e API passam a ter a mesma
// origem, tambem nao ha CORS no caminho.
const servidor = { host: true, port: 5000, proxy };

export default defineConfig({
  plugins: [react()],
  server: servidor,
  // `preview` serve o build de dist/ e e o modo indicado para apresentar:
  // sem HMR, nao ha websocket para cair se a rede oscilar.
  preview: servidor,
});

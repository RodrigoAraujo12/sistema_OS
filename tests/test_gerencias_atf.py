"""
A gerencia de cada equipe fiscal, deduzida do nome da equipe.

A regra ("em `A - B` o B e o nivel acima; na barra `GOFE/GR2` a gerencia
e a GOFE") foi confirmada pela area fiscal em 22/09/2026, e e o que tirou
do zero o corte por gerencia do painel de OS. Os casos abaixo sao nomes
REAIS da planilha da SEFAZ — cada um esta aqui porque quebra uma leitura
ingenua diferente.
"""

from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

from backend.db import Database, EquipeFiscalRepository, GerenciaRepository
from backend.gerencias_atf import (
    EQUIPES_FORA_DO_PAINEL,
    GERENCIAS,
    gerencia_de_equipe,
    gerencias_das_equipes,
)

_MEMORY = Path(":memory:")


class InMemoryDatabase(Database):
    """Database que usa SQLite in-memory para testes (evita locks no Windows)."""

    def __init__(self):
        super().__init__(_MEMORY)
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row

    def connect(self):
        return self._conn


class TestRegraDoNome(unittest.TestCase):
    """Cada nome aqui e um formato real que a planilha usa."""

    def test_traco_com_unidade_a_direita_usa_o_lado_esquerdo(self):
        # 'GOAC - GEFTE' e equipe da GOAC, que RESPONDE a GEFTE. Ler o
        # lado direito daria GEFTE e inverteria a hierarquia.
        self.assertEqual(gerencia_de_equipe("GOAC - GEFTE"), 513)

    def test_traco_com_assunto_a_direita_usa_o_mesmo_lado(self):
        self.assertEqual(gerencia_de_equipe("GOAC - MALHAS"), 513)
        self.assertEqual(gerencia_de_equipe("GOFE - VAREJO"), 254)

    def test_barra_com_regional_fica_com_a_gerencia_e_nao_com_a_regional(self):
        # O ponto que a area fiscal precisou esclarecer: a regional e
        # onde a equipe atua, nao a dona dela.
        self.assertEqual(gerencia_de_equipe("GOFE/GR2 - ESTABELECIMENTOS"), 254)
        self.assertEqual(gerencia_de_equipe("GOFE/GR5 - ESTABELECIMENTOS"), 254)

    def test_barra_dentro_da_propria_sigla_nao_e_recortada(self):
        # GOFITCD/IPVA tem barra no NOME da gerencia. Cortar na barra
        # antes de tentar o nome inteiro daria 'GOFITCD', que nao existe.
        self.assertEqual(gerencia_de_equipe("GOFITCD/IPVA - IPVA"), 512)
        self.assertEqual(gerencia_de_equipe("GOFITCD/IPVA - GEFTE"), 512)

    def test_sufixo_depois_da_sigla_cai_na_primeira_palavra(self):
        # 'GOFSES ST' nao e sigla de nada: ST e o segmento.
        self.assertEqual(gerencia_de_equipe("GOFSES ST - COMBUSTIVEIS"), 275)

    def test_planilha_escreve_a_sigla_diferente_do_elemento(self):
        # A aba de equipes escreve GOFSES; o elemento organizacional e
        # GOFSE. Sao a mesma gerencia (275).
        self.assertEqual(gerencia_de_equipe("GOFSES - GEFTE"), 275)
        self.assertEqual(gerencia_de_equipe("GOFSE - GEFTE"), 275)

    def test_equipe_sem_sigla_nenhuma_e_a_gerencia_por_extenso(self):
        self.assertEqual(
            gerencia_de_equipe("GERENCIA OPERACIONAL DE FISCALIZACAO DE ESTABELECIMENTOS"),
            254,
        )

    def test_acentos_e_caixa_nao_atrapalham(self):
        self.assertEqual(gerencia_de_equipe("GOFE - SERVIÇOS"), 254)
        self.assertEqual(gerencia_de_equipe("gofe - varejo"), 254)

    def test_nome_que_nao_permite_decidir_devolve_none(self):
        # Preferimos ficar sem gerencia a chutar uma: no painel, a
        # ausencia e informacao.
        self.assertIsNone(gerencia_de_equipe("GEST_ITCD_AUDITORES"))
        self.assertIsNone(gerencia_de_equipe("EQUIPE NOVA QUALQUER"))
        self.assertIsNone(gerencia_de_equipe(""))

    def test_toda_gerencia_do_cadastro_tem_codigo_e_sigla_unicos(self):
        codigos = [cod for cod, _, _ in GERENCIAS]
        siglas = [sigla for _, sigla, _ in GERENCIAS]
        self.assertEqual(len(codigos), len(set(codigos)))
        self.assertEqual(len(siglas), len(set(siglas)))


class TestGerenciasDasEquipes(unittest.TestCase):
    """A aplicacao da regra a uma planilha inteira."""

    def test_mapeia_e_avisa_do_que_sobrou(self):
        mapa, avisos = gerencias_das_equipes(
            [(429, "GOAC - MALHAS"), (999, "EQUIPE DESCONHECIDA")]
        )
        self.assertEqual(mapa, {429: 513})
        self.assertEqual(len(avisos), 1)
        self.assertIn("999", avisos[0])

    def test_equipe_excluida_por_decisao_sai_sem_aviso(self):
        # As GEST_ITCD ficam fora do painel por decisao da area fiscal
        # (22/09/2026), nao por falha de leitura: avisar todo import
        # treinaria o operador a ignorar avisos.
        codigo = sorted(EQUIPES_FORA_DO_PAINEL)[0]
        mapa, avisos = gerencias_das_equipes([(codigo, "GEST_ITCD_TECNICOS")])
        self.assertEqual(mapa, {})
        self.assertEqual(avisos, [])


class TestGerenciaNoRepositorio(unittest.TestCase):
    """A gerencia gravada na equipe e lida de volta por matricula."""

    def setUp(self):
        self.db = InMemoryDatabase()
        self.db.init_schema()
        self.repo = EquipeFiscalRepository(self.db)

    def test_substituir_tudo_grava_a_gerencia_da_equipe(self):
        self.repo.substituir_tudo(
            [(429, "GOAC - MALHAS"), (427, "GOFE - VAREJO")],
            [(429, "1000", "FULANO"), (427, "1001", "BELTRANO")],
            gerencias={429: 513, 427: 254},
        )
        self.assertEqual(
            self.repo.get_gerencia_atf_por_matricula(),
            {"1000": 513, "1001": 254},
        )

    def test_equipe_sem_gerencia_nao_entra_no_mapa(self):
        self.repo.substituir_tudo(
            [(613, "GEST_ITCD_TECNICOS")], [(613, "1000", "FULANO")], gerencias={},
        )
        self.assertEqual(self.repo.get_gerencia_atf_por_matricula(), {})

    def test_quem_esta_em_duas_gerencias_aparece_uma_vez_so(self):
        # Sem isso a mesma matricula somaria a OS dela em duas gerencias
        # e o total do corte passaria do total de OS sem explicacao.
        self.repo.substituir_tudo(
            [(429, "GOAC - MALHAS"), (427, "GOFE - VAREJO")],
            [(429, "1000", "FULANO"), (427, "1000", "FULANO")],
            gerencias={429: 513, 427: 254},
        )
        self.assertEqual(self.repo.get_gerencia_atf_por_matricula(), {"1000": 254})

    def test_importacao_nova_substitui_a_gerencia_anterior(self):
        self.repo.substituir_tudo(
            [(429, "GOAC - MALHAS")], [(429, "1000", "FULANO")], gerencias={429: 513},
        )
        self.repo.substituir_tudo(
            [(429, "GOFE - MALHAS")], [(429, "1000", "FULANO")], gerencias={429: 254},
        )
        self.assertEqual(self.repo.get_gerencia_atf_por_matricula(), {"1000": 254})


class TestUpsertGerencia(unittest.TestCase):
    """O cadastro de gerencias casa pelo codigo do ATF, nao pelo nome."""

    def setUp(self):
        self.db = InMemoryDatabase()
        self.db.init_schema()
        self.repo = GerenciaRepository(self.db)

    def test_importar_duas_vezes_nao_duplica(self):
        primeiro = self.repo.upsert_por_codigo_atf(513, "GOAC")
        segundo = self.repo.upsert_por_codigo_atf(513, "GOAC")
        self.assertEqual(primeiro, segundo)
        self.assertEqual(len(self.repo.list_gerencias()), 1)

    def test_nao_desfaz_renomeacao_do_admin(self):
        gid = self.repo.upsert_por_codigo_atf(513, "GOAC")
        self.repo.update_gerencia(gid, "Acompanhamento de Contribuintes")
        self.repo.upsert_por_codigo_atf(513, "GOAC")
        self.assertEqual(
            self.repo.get_gerencia(gid)["name"], "Acompanhamento de Contribuintes"
        )

    def test_gerencia_local_fica_sem_codigo_atf(self):
        gid = self.repo.create_gerencia("Gerencia criada a mao")
        self.assertIsNone(self.repo.get_gerencia(gid)["codigo_atf"])

    def test_varias_gerencias_locais_convivem_com_codigo_nulo(self):
        # O indice unico de codigo_atf e parcial justamente para isso.
        self.repo.create_gerencia("Uma")
        self.repo.create_gerencia("Outra")
        self.assertEqual(len(self.repo.list_gerencias()), 2)


class TestMapaDoPainel(unittest.TestCase):
    """
    A ordem das tres vias em _gerencia_por_matricula.

    Testado com os repositorios trocados por dublês: o que importa aqui e
    a precedencia entre as vias, nao o SQL de cada uma — esse ja tem teste
    proprio acima.
    """

    def _montar(self, gerencias, lotados, por_equipe_do_supervisor, gerencia_da_equipe):
        from unittest.mock import MagicMock, patch

        g_repo, u_repo, e_repo = MagicMock(), MagicMock(), MagicMock()
        g_repo.list_gerencias.return_value = gerencias
        u_repo.get_matriculas_by_gerencia.side_effect = lambda gid: lotados.get(gid, [])
        u_repo.get_equipe_codigos_by_gerencia.side_effect = (
            lambda gid: list(por_equipe_do_supervisor.get(gid, {}))
        )
        e_repo.get_matriculas_by_equipes.side_effect = lambda codigos: [
            m
            for mapa in por_equipe_do_supervisor.values()
            for cod, membros in mapa.items()
            if cod in codigos
            for m in membros
        ]
        e_repo.get_gerencia_atf_por_matricula.return_value = gerencia_da_equipe

        from backend import main

        with patch.object(main, "gerencia_repo", g_repo), \
             patch.object(main, "user_repo", u_repo), \
             patch.object(main, "equipe_repo", e_repo):
            return main._gerencia_por_matricula()

    def test_lotacao_direta_ganha_da_equipe(self):
        # O admin dizer onde a pessoa esta vale mais que deduzir pelo
        # nome da equipe dela.
        mapa = self._montar(
            gerencias=[
                {"id": 1, "name": "Lotacao local", "codigo_atf": None},
                {"id": 6, "name": "GOFE", "codigo_atf": 254},
            ],
            lotados={1: ["1000"]},
            por_equipe_do_supervisor={},
            gerencia_da_equipe={"1000": 254, "1001": 254},
        )
        self.assertEqual(mapa["1000"]["nome"], "Lotacao local")
        self.assertEqual(mapa["1001"]["nome"], "GOFE")

    def test_equipe_alcanca_quem_nao_tem_lotacao(self):
        # A via que tirou o corte do zero: 334 auditores importados sem
        # lotacao nenhuma passam a ter gerencia pela equipe.
        mapa = self._montar(
            gerencias=[{"id": 6, "name": "GOFE", "codigo_atf": 254}],
            lotados={},
            por_equipe_do_supervisor={},
            gerencia_da_equipe={"1001": 254, "1002": 254},
        )
        self.assertEqual(len(mapa), 2)

    def test_gerencia_do_atf_fora_do_cadastro_e_ignorada(self):
        # Sem isso, uma gerencia que ninguem consegue abrir na tela de
        # cadastro viraria linha no grafico.
        mapa = self._montar(
            gerencias=[{"id": 6, "name": "GOFE", "codigo_atf": 254}],
            lotados={},
            por_equipe_do_supervisor={},
            gerencia_da_equipe={"1001": 999},
        )
        self.assertEqual(mapa, {})


if __name__ == "__main__":
    unittest.main()

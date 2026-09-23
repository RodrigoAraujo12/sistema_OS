"""
Testes das equipes fiscais do ATF: leitura da planilha da SEFAZ e o
repositorio que a armazena.

A visibilidade de OS por equipe (quem enxerga o que) e testada em
test_integration.py, junto com o resto do controle de acesso.
"""

from __future__ import annotations

import sqlite3
import unittest
import zipfile
from pathlib import Path

from backend.db import Database, EquipeFiscalRepository, UserRepository
from backend.db import GerenciaRepository
from backend.importar_equipes import (
    COR_CABECALHO,
    COR_SUPERVISOR,
    Celula,
    _numero,
    extrair,
    extrair_supervisores,
    planejar_amarracao,
    planejar_lotacao,
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


def _linha(codigo=None, grupo=None, matricula=None, nome=None, cor="") -> dict[str, str]:
    """
    Monta uma linha da aba no formato que _ler_aba devolve.

    `cor` pinta matricula e nome, que e onde a planilha da SEFAZ marca a
    chefia — as colunas de codigo e grupo ficam sempre sem cor.
    """
    celulas = {}
    if codigo is not None:
        celulas["A"] = codigo
    if grupo is not None:
        celulas["B"] = grupo
    if matricula is not None:
        celulas["C"] = Celula(matricula, cor)
    if nome is not None:
        celulas["D"] = Celula(nome, cor)
    return celulas


class TestNumero(unittest.TestCase):
    """Conversao dos numeros que o Excel guarda com casa decimal."""

    def test_tira_casa_decimal(self):
        self.assertEqual(_numero("604.0"), "604")
        self.assertEqual(_numero("9000001.0"), "9000001")

    def test_aceita_inteiro_puro(self):
        self.assertEqual(_numero("427"), "427")

    def test_vazio_e_none(self):
        self.assertIsNone(_numero(None))
        self.assertIsNone(_numero(""))
        self.assertIsNone(_numero("   "))

    def test_descarta_nao_numerico(self):
        """Texto no lugar de matricula e descartado, nao adivinhado."""
        self.assertIsNone(_numero("Código"))
        self.assertIsNone(_numero("Atualizado em: 21/082026"))

    def test_descarta_fracionario(self):
        """Matricula com fracao e dado corrompido — melhor perder a linha."""
        self.assertIsNone(_numero("604.5"))


class TestExtrair(unittest.TestCase):
    """Limpeza das sujeiras da exportacao paginada da SEFAZ."""

    def test_caso_simples(self):
        equipes, membros, avisos = extrair([
            _linha("Código", "Grupo", "Matrícula", "Fiscal"),
            _linha("427.0", "GOFE - VAREJO", "9000001.0", "FULANO DE TAL"),
        ])
        self.assertEqual(equipes, [(427, "GOFE - VAREJO")])
        self.assertEqual(membros, [(427, "9000001", "FULANO DE TAL")])
        self.assertEqual(avisos, [])

    def test_descarta_cabecalho_repetido(self):
        """
        A exportacao repete o cabecalho a cada pagina. Sem descartar,
        "Código/Grupo/Matrícula/Fiscal" viraria um auditor.
        """
        linhas = [_linha("Código", "Grupo", "Matrícula", "Fiscal")]
        for i in range(3):
            linhas.append(_linha("427.0", "GOFE - VAREJO", f"100{i}.0", f"FISCAL {i}"))
            linhas.append(_linha("Código", "Grupo", "Matrícula", "Fiscal"))

        equipes, membros, avisos = extrair(linhas)
        self.assertEqual(len(equipes), 1)
        self.assertEqual(len(membros), 3)
        self.assertEqual(avisos, [])
        self.assertNotIn("Fiscal", [nome for _, _, nome in membros])

    def test_descarta_rodape_sem_codigo(self):
        """A ultima linha da planilha e "Atualizado em: ...", so na coluna B."""
        equipes, membros, avisos = extrair([
            _linha("427.0", "GOFE - VAREJO", "9000001.0", "FULANO"),
            _linha(grupo="Atualizado em: 21/082026"),
        ])
        self.assertEqual(len(equipes), 1)
        self.assertEqual(len(membros), 1)
        self.assertEqual(avisos, [])

    def test_auditor_em_duas_equipes_vira_dois_vinculos(self):
        """
        Cinco auditores da planilha real estao em duas equipes. Os dois
        vinculos sao legitimos: cada supervisor enxerga essa pessoa.
        """
        equipes, membros, _ = extrair([
            _linha("614.0", "GEST_ITCD_AUDITORES", "9000002.0", "BELTRANO DA SILVA"),
            _linha("554.0", "GOFITCD/IPVA - GEFTE", "9000002.0", "BELTRANO DA SILVA"),
        ])
        self.assertEqual(len(equipes), 2)
        self.assertEqual(len(membros), 2)
        self.assertEqual({cod for cod, _, _ in membros}, {614, 554})

    def test_linha_repetida_nao_duplica(self):
        """A mesma pessoa na mesma equipe duas vezes conta uma so."""
        _, membros, _ = extrair([
            _linha("427.0", "GOFE - VAREJO", "9000001.0", "FULANO"),
            _linha("427.0", "GOFE - VAREJO", "9000001.0", "FULANO"),
        ])
        self.assertEqual(len(membros), 1)

    def test_avisa_sobre_linha_sem_matricula(self):
        _, membros, avisos = extrair([
            _linha("427.0", "GOFE - VAREJO", None, "SEM MATRICULA"),
        ])
        self.assertEqual(membros, [])
        self.assertEqual(len(avisos), 1)
        self.assertIn("sem matricula", avisos[0])

    def test_avisa_sobre_equipe_com_dois_nomes(self):
        """Mesmo codigo com nomes diferentes e sinal de planilha inconsistente."""
        equipes, _, avisos = extrair([
            _linha("427.0", "GOFE - VAREJO", "1000.0", "A"),
            _linha("427.0", "GOFE - VAREJO (NOVO)", "1001.0", "B"),
        ])
        self.assertEqual(equipes, [(427, "GOFE - VAREJO")])
        self.assertEqual(len(avisos), 1)
        self.assertIn("dois nomes", avisos[0])

    def test_planilha_vazia(self):
        equipes, membros, avisos = extrair([])
        self.assertEqual((equipes, membros, avisos), ([], [], []))


class TestExtrairSupervisores(unittest.TestCase):
    """
    A chefia so existe na cor de fundo da celula: a planilha de
    02/09/2026 pinta matricula e nome de amarelo dentro do bloco do
    grupo, sem coluna que diga quem e.
    """

    def test_marca_apenas_quem_esta_pintado(self):
        linhas = [
            _linha("Código", "Grupo", "Matrícula", "Fiscal", cor=COR_CABECALHO),
            _linha("427.0", "GOFE - VAREJO", "9000001.0", "CHEFE", cor=COR_SUPERVISOR),
            _linha("427.0", "GOFE - VAREJO", "9000002.0", "MEMBRO"),
        ]
        _, membros, _ = extrair(linhas)
        supervisores, avisos = extrair_supervisores(linhas, membros)
        self.assertEqual(supervisores, [(427, "9000001", "CHEFE")])
        self.assertEqual(avisos, [])

    def test_cabecalho_pintado_nao_vira_pessoa(self):
        """
        So entra quem sobreviveu a `extrair`. O cabecalho se repete a cada
        grupo, e sem esse filtro viraria um supervisor chamado "Fiscal".
        """
        linhas = [
            _linha("Código", "Grupo", "Matrícula", "Fiscal", cor=COR_SUPERVISOR),
            _linha("427.0", "GOFE - VAREJO", "9000002.0", "MEMBRO"),
        ]
        _, membros, _ = extrair(linhas)
        supervisores, _ = extrair_supervisores(linhas, membros)
        self.assertEqual(supervisores, [])

    def test_uma_pessoa_pode_chefiar_duas_equipes(self):
        """A planilha de 02/09/2026 tem dois casos assim; sao legitimos."""
        linhas = [
            _linha("423.0", "GOFE/GR5", "9000001.0", "CHEFE", cor=COR_SUPERVISOR),
            _linha("434.0", "GOFE/GR4", "9000001.0", "CHEFE", cor=COR_SUPERVISOR),
        ]
        _, membros, _ = extrair(linhas)
        supervisores, _ = extrair_supervisores(linhas, membros)
        self.assertEqual(
            supervisores, [(423, "9000001", "CHEFE"), (434, "9000001", "CHEFE")]
        )

    def test_avisa_quando_nao_ha_marca_nenhuma(self):
        """
        Zero chefias e ambiguo: pode ser planilha antiga ou formatacao
        perdida numa reexportacao. Nos dois casos o operador precisa saber.
        """
        linhas = [_linha("427.0", "GOFE - VAREJO", "9000002.0", "MEMBRO")]
        _, membros, _ = extrair(linhas)
        supervisores, avisos = extrair_supervisores(linhas, membros)
        self.assertEqual(supervisores, [])
        self.assertTrue(any("nenhuma chefia" in a for a in avisos))

    def test_avisa_cor_desconhecida(self):
        """Se a SEFAZ trocar o tom do amarelo, isso aparece em vez de sumir."""
        linhas = [
            _linha("427.0", "GOFE - VAREJO", "9000001.0", "CHEFE", cor="00FF00"),
            _linha("427.0", "GOFE - VAREJO", "9000002.0", "OUTRO", cor=COR_SUPERVISOR),
        ]
        _, membros, _ = extrair(linhas)
        supervisores, avisos = extrair_supervisores(linhas, membros)
        self.assertEqual(supervisores, [(427, "9000002", "OUTRO")])
        self.assertTrue(any("00FF00" in a for a in avisos))

    def test_planilha_sem_cor_alguma_nao_quebra(self):
        """Celula de texto puro (planilha antiga) segue valendo como membro."""
        linhas = [{"A": "427.0", "B": "GOFE", "C": "9000001.0", "D": "FULANO"}]
        _, membros, _ = extrair(linhas)
        supervisores, _ = extrair_supervisores(linhas, membros)
        self.assertEqual(supervisores, [])


class TestPlanejarAmarracao(unittest.TestCase):
    """
    Cruzamento da chefia da planilha com os usuarios do banco.

    `users.equipe_codigo` guarda um codigo so, e so tem efeito para quem e
    supervisor — por isso amarrar envolve promover, e por isso quem chefia
    duas equipes nao pode ser resolvido no palpite.
    """

    def setUp(self):
        self.db = InMemoryDatabase()
        self.db.init_schema()
        self.users = UserRepository(self.db)
        EquipeFiscalRepository(self.db).substituir_tudo(
            [(427, "GOFE - VAREJO"), (429, "GOAC - MALHAS")], [],
        )
        self.nomes = {427: "GOFE - VAREJO", 429: "GOAC - MALHAS"}

    def _criar(self, username, matricula, role="fiscal", equipe=None):
        return self.users.create_user(
            username, "hash", "salt", role, None, None, False, matricula, equipe,
        )

    def test_promove_fiscal_e_amarra_a_equipe(self):
        self._criar("chefe", "1000")
        a_amarrar, ja_ok, impedidos = planejar_amarracao(
            self.users, [(427, "1000", "CHEFE")], self.nomes
        )
        self.assertEqual(a_amarrar, [("1000", "CHEFE", 427, "GOFE - VAREJO", "fiscal")])
        self.assertEqual((ja_ok, impedidos), ([], []))

        self.assertTrue(
            self.users.amarrar_equipe_por_matricula("1000", 427, promover=True)
        )
        usuario = self.users.get_user_by_matricula("1000")
        self.assertEqual(usuario["role"], "supervisor")
        self.assertEqual(usuario["equipe_codigo"], 427)

    def test_quem_chefia_duas_equipes_e_promovido_sem_equipe(self):
        """
        `equipe_codigo` guarda um codigo so, entao fica vazio: a chefia
        dele vem inteira de `equipe_membros.supervisor`, e escolher uma
        das duas o deixaria cego para metade do que e dele.
        """
        self._criar("chefe", "1000")
        a_amarrar, _, impedidos = planejar_amarracao(
            self.users, [(427, "1000", "CHEFE"), (429, "1000", "CHEFE")], self.nomes
        )
        self.assertEqual(impedidos, [])
        (matricula, _, codigo, descricao, papel) = a_amarrar[0]
        self.assertEqual((matricula, codigo, papel), ("1000", None, "fiscal"))
        self.assertIn("GOAC - MALHAS", descricao)

        self.assertTrue(
            self.users.amarrar_equipe_por_matricula("1000", None, promover=True)
        )
        usuario = self.users.get_user_by_matricula("1000")
        self.assertEqual(usuario["role"], "supervisor")
        self.assertIsNone(usuario["equipe_codigo"])

    def test_promover_sem_equipe_nao_apaga_amarracao_manual(self):
        """Passar None e "nao mexe na coluna", nao "limpa a coluna"."""
        self._criar("chefe", "1000", role="fiscal", equipe=429)
        self.users.amarrar_equipe_por_matricula("1000", None, promover=True)
        usuario = self.users.get_user_by_matricula("1000")
        self.assertEqual(usuario["role"], "supervisor")
        self.assertEqual(usuario["equipe_codigo"], 429)

    def test_supervisor_sem_login_fica_de_fora(self):
        a_amarrar, _, impedidos = planejar_amarracao(
            self.users, [(427, "1000", "CHEFE")], self.nomes
        )
        self.assertEqual(a_amarrar, [])
        self.assertTrue(any("sem usuario cadastrado" in m for m in impedidos))

    def test_gerente_nao_e_rebaixado_a_supervisor(self):
        """O papel do cadastro local manda mais do que a marca da planilha."""
        self._criar("gerente", "1000", role="gerente")
        a_amarrar, _, impedidos = planejar_amarracao(
            self.users, [(427, "1000", "CHEFE")], self.nomes
        )
        self.assertEqual(a_amarrar, [])
        self.assertTrue(any("e gerente" in m for m in impedidos))
        self.users.amarrar_equipe_por_matricula("1000", 427, promover=True)
        self.assertEqual(self.users.get_user_by_matricula("1000")["role"], "gerente")

    def test_quem_ja_esta_correto_nao_entra_na_lista(self):
        self._criar("chefe", "1000", role="supervisor", equipe=427)
        a_amarrar, ja_ok, impedidos = planejar_amarracao(
            self.users, [(427, "1000", "CHEFE")], self.nomes
        )
        self.assertEqual((a_amarrar, impedidos), ([], []))
        self.assertEqual(len(ja_ok), 1)
        self.assertFalse(
            self.users.amarrar_equipe_por_matricula("1000", 427, promover=True)
        )


class TestPlanejarLotacao(unittest.TestCase):
    """
    Preenchimento de `users.gerencia_id` pela gerencia da equipe fiscal.

    E a mesma ponte que o painel usa para o corte por gerencia, mas com
    uma exigencia a mais: aqui o resultado fica GRAVADO no cadastro,
    entao nao ha desempate no palpite — quem esta em equipes de gerencias
    diferentes fica para o admin resolver na tela.
    """

    # GOAC e GOFE, pelos codigos dos elementos organizacionais.
    GOAC, GOFE = 513, 254

    def setUp(self):
        self.db = InMemoryDatabase()
        self.db.init_schema()
        self.users = UserRepository(self.db)
        self.gerencias = GerenciaRepository(self.db)
        self.equipes = EquipeFiscalRepository(self.db)
        self.id_goac = self.gerencias.upsert_por_codigo_atf(self.GOAC, "GOAC")
        self.equipes.substituir_tudo(
            [(429, "GOAC - MALHAS"), (427, "GOFE - VAREJO")],
            [(429, "1000", "FULANO"), (427, "2000", "BELTRANO")],
            gerencias={429: self.GOAC, 427: self.GOFE},
        )

    def _criar(self, username, matricula, role="fiscal", gerencia_id=None):
        return self.users.create_user(
            username, "hash", "salt", role, gerencia_id, None, False, matricula, None,
        )

    def _planejar(self):
        return planejar_lotacao(self.users, self.gerencias, self.equipes)

    def test_lota_pela_gerencia_da_equipe(self):
        self._criar("FULANO", "1000")
        a_lotar, ja_ok, impedidos = self._planejar()
        self.assertEqual(a_lotar, [("1000", "FULANO", self.id_goac, "GOAC")])
        self.assertEqual((ja_ok, impedidos), ([], []))

        self.assertTrue(self.users.lotar_gerencia_por_matricula("1000", self.id_goac))
        self.assertEqual(
            self.users.get_user_by_matricula("1000")["gerencia_id"], self.id_goac
        )

    def test_nao_sobrescreve_lotacao_feita_a_mao(self):
        """O que o admin disse na tela manda mais do que a deducao."""
        outra = self.gerencias.create_gerencia("Gerencia local")
        self._criar("FULANO", "1000", gerencia_id=outra)
        a_lotar, ja_ok, _ = self._planejar()
        self.assertEqual(a_lotar, [])
        self.assertEqual(len(ja_ok), 1)

        self.assertFalse(self.users.lotar_gerencia_por_matricula("1000", self.id_goac))
        self.assertEqual(self.users.get_user_by_matricula("1000")["gerencia_id"], outra)

    def test_em_duas_gerencias_fica_para_o_admin(self):
        self.equipes.substituir_tudo(
            [(429, "GOAC - MALHAS"), (427, "GOFE - VAREJO")],
            [(429, "1000", "FULANO"), (427, "1000", "FULANO")],
            gerencias={429: self.GOAC, 427: self.GOFE},
        )
        self.gerencias.upsert_por_codigo_atf(self.GOFE, "GOFE")
        self._criar("FULANO", "1000")
        a_lotar, _, impedidos = self._planejar()
        self.assertEqual(a_lotar, [])
        self.assertTrue(any("em equipes de 2 gerencias" in m for m in impedidos))
        self.assertIsNone(self.users.get_user_by_matricula("1000")["gerencia_id"])

    def test_gerencia_fora_do_cadastro_nao_lota(self):
        """A GOFE existe na equipe, mas nao no cadastro local."""
        self._criar("BELTRANO", "2000")
        a_lotar, _, impedidos = self._planejar()
        self.assertEqual(a_lotar, [])
        self.assertTrue(any("ainda nao esta no cadastro" in m for m in impedidos))

    def test_quem_nao_tem_login_e_ignorado_em_silencio(self):
        """
        A planilha alcanca 334 auditores e nem todos precisam de login
        aqui: isso nao e pendencia, entao nao vira aviso.
        """
        a_lotar, ja_ok, impedidos = self._planejar()
        self.assertEqual((a_lotar, ja_ok, impedidos), ([], [], []))

    def test_equipe_sem_gerencia_nao_lota(self):
        """As duas equipes que a area fiscal deixou fora do painel."""
        self.equipes.substituir_tudo(
            [(613, "GEST - ALGO")], [(613, "1000", "FULANO")], gerencias={},
        )
        self._criar("FULANO", "1000")
        a_lotar, _, impedidos = self._planejar()
        self.assertEqual((a_lotar, impedidos), ([], []))
        self.assertIsNone(self.users.get_user_by_matricula("1000")["gerencia_id"])


class TestEquipeFiscalRepository(unittest.TestCase):
    """Armazenamento das equipes e seus membros."""

    def setUp(self):
        self.db = InMemoryDatabase()
        self.db.init_schema()
        self.repo = EquipeFiscalRepository(self.db)

    def test_schema_cria_tabelas(self):
        nomes = {
            t["name"]
            for t in self.db.connect().execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        self.assertIn("equipes_fiscais", nomes)
        self.assertIn("equipe_membros", nomes)

    def test_substituir_e_ler(self):
        self.repo.substituir_tudo(
            [(427, "GOFE - VAREJO")],
            [(427, "1000", "FULANO"), (427, "1001", "BELTRANO")],
        )
        self.assertEqual(self.repo.count_equipes(), 1)
        self.assertEqual(
            set(self.repo.get_matriculas_by_equipe(427)), {"1000", "1001"}
        )

    def test_grava_quem_chefia_a_equipe(self):
        self.repo.substituir_tudo(
            [(427, "GOFE - VAREJO")],
            [(427, "1000", "CHEFE"), (427, "1001", "MEMBRO")],
            {(427, "1000")},
        )
        membros = self.repo.get_membros(427)
        # get_membros poe a chefia na frente, e so depois ordena por nome
        self.assertEqual(membros[0]["nome"], "CHEFE")
        self.assertEqual(membros[0]["supervisor"], 1)
        self.assertEqual(membros[1]["supervisor"], 0)

    def test_sem_chefia_todo_mundo_e_membro(self):
        """Planilha ate 25/08/2026 nao trazia a informacao — e valido."""
        self.repo.substituir_tudo(
            [(427, "GOFE - VAREJO")], [(427, "1000", "FULANO")],
        )
        self.assertEqual(self.repo.get_membros(427)[0]["supervisor"], 0)

    def test_chefia_tambem_e_substituida(self):
        """Quem deixou de chefiar na carga nova nao continua chefiando."""
        self.repo.substituir_tudo(
            [(427, "A")], [(427, "1000", "ANTIGO")], {(427, "1000")},
        )
        self.repo.substituir_tudo([(427, "A")], [(427, "1000", "ANTIGO")])
        self.assertEqual(self.repo.get_membros(427)[0]["supervisor"], 0)

    def test_consulta_as_equipes_que_a_matricula_chefia(self):
        self.repo.substituir_tudo(
            [(427, "GOFE - VAREJO"), (429, "GOAC - MALHAS")],
            [
                (427, "1000", "CHEFE DOS DOIS"),
                (429, "1000", "CHEFE DOS DOIS"),
                (427, "1001", "MEMBRO"),
            ],
            {(427, "1000"), (429, "1000")},
        )
        self.assertEqual(self.repo.get_codigos_chefiados("1000"), [427, 429])
        self.assertEqual(self.repo.get_codigos_chefiados("1001"), [])
        mapa = self.repo.get_chefias_por_matricula()
        self.assertEqual([e["nome"] for e in mapa["1000"]], ["GOAC - MALHAS", "GOFE - VAREJO"])
        self.assertNotIn("1001", mapa)

    def test_substituir_apaga_o_que_saiu(self):
        """
        Carga nova substitui a anterior por completo. Se fosse merge,
        quem saiu da equipe continuaria visivel para o supervisor.
        """
        self.repo.substituir_tudo(
            [(427, "GOFE - VAREJO")], [(427, "1000", "SAIU"), (427, "1001", "FICOU")]
        )
        self.repo.substituir_tudo(
            [(427, "GOFE - VAREJO")], [(427, "1001", "FICOU")]
        )
        self.assertEqual(self.repo.get_matriculas_by_equipe(427), ["1001"])

    def test_equipe_extinta_some(self):
        self.repo.substituir_tudo([(427, "A"), (429, "B")], [])
        self.repo.substituir_tudo([(427, "A")], [])
        self.assertIsNone(self.repo.get_equipe(429))
        self.assertEqual(self.repo.get_matriculas_by_equipe(429), [])

    def test_equipe_inexistente_nao_da_acesso(self):
        """Codigo que nao existe devolve conjunto vazio, nunca 'tudo'."""
        self.assertEqual(self.repo.get_matriculas_by_equipe(9999), [])

    def test_mesma_matricula_em_duas_equipes(self):
        self.repo.substituir_tudo(
            [(614, "ITCD"), (554, "IPVA")],
            [(614, "9000002", "BELTRANO"), (554, "9000002", "BELTRANO")],
        )
        self.assertEqual(self.repo.get_matriculas_by_equipe(614), ["9000002"])
        self.assertEqual(self.repo.get_matriculas_by_equipe(554), ["9000002"])

    def test_list_equipes_conta_membros(self):
        self.repo.substituir_tudo(
            [(427, "GOFE - VAREJO"), (429, "GOAC - MALHAS")],
            [(427, "1000", "A"), (427, "1001", "B"), (429, "1002", "C")],
        )
        por_codigo = {e["codigo"]: e for e in self.repo.list_equipes()}
        self.assertEqual(por_codigo[427]["total_membros"], 2)
        self.assertEqual(por_codigo[429]["total_membros"], 1)

    def test_list_equipes_inclui_equipe_vazia(self):
        """Equipe sem ninguem ainda aparece na lista, com contagem zero."""
        self.repo.substituir_tudo([(427, "GOFE - VAREJO")], [])
        equipes = self.repo.list_equipes()
        self.assertEqual(len(equipes), 1)
        self.assertEqual(equipes[0]["total_membros"], 0)

    def test_get_membros_traz_nome(self):
        self.repo.substituir_tudo(
            [(427, "GOFE - VAREJO")], [(427, "1000", "ZEZINHO"), (427, "1001", "ANA")]
        )
        membros = self.repo.get_membros(427)
        self.assertEqual([m["nome"] for m in membros], ["ANA", "ZEZINHO"])


class TestPlanilhaReal(unittest.TestCase):
    """
    Le a planilha da SEFAZ, se ela estiver disponivel.

    Fica como skip no CI e na maquina de quem nao tem o arquivo: ele nao
    e versionado, por conter nome e matricula de servidor.
    """

    CAMINHOS = [
        Path.home() / "Downloads" / "DADOS_ORDEM_SERVICO.xlsx",
        Path(__file__).parent / "dados" / "DADOS_ORDEM_SERVICO.xlsx",
    ]

    def setUp(self):
        self.planilha = next((c for c in self.CAMINHOS if c.is_file()), None)
        if self.planilha is None:
            self.skipTest("planilha da SEFAZ nao disponivel nesta maquina")

    def test_le_a_aba_de_grupos(self):
        from backend.importar_equipes import ABA_GRUPOS, _ler_aba

        equipes, membros, avisos = extrair(_ler_aba(self.planilha, ABA_GRUPOS))
        self.assertGreater(len(equipes), 0)
        self.assertGreater(len(membros), len(equipes))
        self.assertEqual(avisos, [])
        # Nenhum cabecalho ou rodape sobreviveu a limpeza
        nomes = {nome for _, _, nome in membros}
        self.assertNotIn("Fiscal", nomes)
        self.assertTrue(all(m.isdigit() for _, m, _ in membros))

    def test_aba_inexistente_da_erro_util(self):
        from backend.importar_equipes import _ler_aba

        with self.assertRaises(ValueError) as ctx:
            _ler_aba(self.planilha, "Aba Que Nao Existe")
        self.assertIn("Abas na planilha", str(ctx.exception))

    def test_arquivo_invalido(self):
        from backend.importar_equipes import ABA_GRUPOS, _ler_aba

        with self.assertRaises(zipfile.BadZipFile):
            _ler_aba(Path(__file__), ABA_GRUPOS)


if __name__ == "__main__":
    unittest.main()

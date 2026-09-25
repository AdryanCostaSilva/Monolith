# TODO: separar este arquivo nos módulos definidos na arquitetura (PBL 4):
#   - src/entrada/loader.py        -> leitura e validação do dataset
#   - src/profiling/profiler.py    -> cálculo de tipos, ausentes, únicos, estatísticas
#   - src/avaliacao/*.py           -> avaliadores por dimensão (Completude, Consistência etc.)
#   - src/agregacao/agregador.py   -> normalização e cálculo do Data Readiness Score
#   - src/relatorio/gerador_relatorio.py -> montagem do resultado final
#   - src/ui/main_window.py        -> esta classe DataReadinessApp, sem lógica de análise
# Por enquanto está tudo em um único arquivo apenas para fins de demonstração (PBL 5).

import customtkinter as ctk
from tkinter import filedialog
import pandas as pd

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class DataReadinessApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Data Readiness Framework")
        self.geometry("900x650")
        self.minsize(700, 500)

        self.df = None

        self._montar_interface()

    def _montar_interface(self):
        # Cabeçalho
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(20, 10))

        titulo = ctk.CTkLabel(
            header,
            text="Data Readiness Framework",
            font=ctk.CTkFont(size=22, weight="bold")
        )
        titulo.pack(side="left")

        self.btn_upload = ctk.CTkButton(
            header,
            text="📂 Carregar Dataset",
            command=self.carregar_dataset,
            width=180
        )
        self.btn_upload.pack(side="right")

        # Status do dataset carregado
        self.label_status = ctk.CTkLabel(
            self,
            text="Nenhum dataset carregado.",
            font=ctk.CTkFont(size=13),
            text_color="gray"
        )
        self.label_status.pack(anchor="w", padx=20, pady=(0, 10))

        # Cards de resumo (linhas, colunas, % ausentes)
        cards_frame = ctk.CTkFrame(self, fg_color="transparent")
        cards_frame.pack(fill="x", padx=20, pady=(0, 15))

        self.card_linhas = self._criar_card(cards_frame, "Linhas", "-")
        self.card_colunas = self._criar_card(cards_frame, "Colunas", "-")
        self.card_ausentes = self._criar_card(cards_frame, "% Ausentes", "-")

        # Área de resultado detalhado (profiling)
        self.textbox_resultado = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Consolas", size=13)
        )
        self.textbox_resultado.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        self.textbox_resultado.insert(
            "1.0",
            "Carregue um dataset (.csv ou .xlsx) para visualizar o profiling básico."
        )
        self.textbox_resultado.configure(state="disabled")

    def _criar_card(self, parent, titulo, valor_inicial):
        card = ctk.CTkFrame(parent, corner_radius=10)
        card.pack(side="left", expand=True, fill="x", padx=5)

        label_titulo = ctk.CTkLabel(
            card, text=titulo, font=ctk.CTkFont(size=12), text_color="gray"
        )
        label_titulo.pack(pady=(10, 0))

        label_valor = ctk.CTkLabel(
            card, text=valor_inicial, font=ctk.CTkFont(size=20, weight="bold")
        )
        label_valor.pack(pady=(0, 10))

        card.label_valor = label_valor
        return card

    def carregar_dataset(self):
        caminho = filedialog.askopenfilename(
            filetypes=[("CSV files", "*.csv"), ("Excel files", "*.xlsx")]
        )
        if not caminho:
            return

        try:
            if caminho.endswith(".csv"):
                self.df = pd.read_csv(caminho)
            else:
                self.df = pd.read_excel(caminho)
        except Exception as e:
            self._exibir_erro(f"Erro ao carregar o arquivo: {e}")
            return

        nome_arquivo = caminho.split("/")[-1]
        self.label_status.configure(
            text=f"Dataset carregado: {nome_arquivo}",
            text_color="lightgreen"
        )

        self._atualizar_cards()
        self._mostrar_profiling()

    def _atualizar_cards(self):
        linhas, colunas = self.df.shape
        total_celulas = linhas * colunas
        pct_ausentes = (self.df.isnull().sum().sum() / total_celulas) * 100

        self.card_linhas.label_valor.configure(text=str(linhas))
        self.card_colunas.label_valor.configure(text=str(colunas))
        self.card_ausentes.label_valor.configure(text=f"{pct_ausentes:.1f}%")

    def _mostrar_profiling(self):
        texto = "=== TIPOS DE COLUNAS ===\n"
        texto += str(self.df.dtypes) + "\n\n"

        texto += "=== VALORES AUSENTES POR COLUNA ===\n"
        texto += str(self.df.isnull().sum()) + "\n\n"

        texto += "=== VALORES ÚNICOS POR COLUNA ===\n"
        texto += str(self.df.nunique()) + "\n\n"

        texto += "=== ESTATÍSTICAS DESCRITIVAS ===\n"
        texto += str(self.df.describe())

        self.textbox_resultado.configure(state="normal")
        self.textbox_resultado.delete("1.0", "end")
        self.textbox_resultado.insert("1.0", texto)
        self.textbox_resultado.configure(state="disabled")

    def _exibir_erro(self, mensagem):
        self.textbox_resultado.configure(state="normal")
        self.textbox_resultado.delete("1.0", "end")
        self.textbox_resultado.insert("1.0", mensagem)
        self.textbox_resultado.configure(state="disabled")


if __name__ == "__main__":
    app = DataReadinessApp()
    app.mainloop()
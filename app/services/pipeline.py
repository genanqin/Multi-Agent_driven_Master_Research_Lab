from app.agents.debate import MAADDebate
from app.agents.judge import InvestmentManagerAgent
from app.agents.masters import MasterAgentOrchestrator
from app.agents.signals import FundamentalAgent, MarketTechnicalAgent, NewsSentimentAgent
from app.models.schemas import AnalyzeRequest, AnalyzeResponse
from app.services.data_provider import DataProvider
from app.services.llm_client import LLMClient


class QuantPipeline:
    def __init__(self) -> None:
        self.data_provider = DataProvider()
        self.technical_agent = MarketTechnicalAgent()
        self.fundamental_agent = FundamentalAgent()
        self.news_agent = NewsSentimentAgent()
        self.master_orchestrator = MasterAgentOrchestrator()
        self.debate = MAADDebate()
        self.judge = InvestmentManagerAgent()

    def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        LLMClient.clear_recent_errors()
        resolved_symbols = self.data_provider.resolve_symbols(request.symbols)
        effective_request = AnalyzeRequest(symbols=resolved_symbols, capital=request.capital)
        dataset = self.data_provider.load(effective_request.symbols)
        technicals = self.technical_agent.analyze(dataset.history)
        fundamentals = self.fundamental_agent.analyze(dataset.fundamentals)
        news = self.news_agent.analyze(dataset.news)
        master_opinions = self.master_orchestrator.analyze(technicals, fundamentals, news)
        debate = self.debate.run(master_opinions)
        portfolio, cash, summary = self.judge.allocate(request.capital, dataset.prices, fundamentals, news, master_opinions, debate)
        llm_errors = LLMClient.consume_recent_errors()
        llm_note = ""
        if llm_errors:
            llm_note = f" LLM提示：外部模型调用异常，相关内容已自动回退本地规则或模板（最近错误 {len(llm_errors)} 条）。"
        return AnalyzeResponse(
            request=effective_request,
            prices=dataset.prices,
            technical_signals=technicals,
            fundamental_signals=fundamentals,
            news_signals=news,
            master_opinions=master_opinions,
            debate=debate,
            portfolio=portfolio,
            cash=cash,
            summary=f"{summary}{llm_note} 数据源：{dataset.data_note}。",
        )

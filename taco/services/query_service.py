"""
自然言語クエリ処理サービス
"""
import logging
import json
from typing import List, Dict, Any, Optional, Union
from enum import Enum, auto
from dataclasses import dataclass
import re

import google.generativeai as genai
import boto3

from taco.config.settings import get_settings
from taco.models.task import Task

logger = logging.getLogger(__name__)

class QueryIntent(Enum):
    """
    クエリの意図
    """
    TASKS_DUE_TODAY = auto()
    TASKS_DUE_THIS_WEEK = auto()
    TASKS_OVERDUE = auto()
    TASKS_BY_ASSIGNEE = auto()
    PROJECT_STATUS = auto()
    UNKNOWN = auto()


@dataclass
class QueryContext:
    """
    クエリのコンテキスト情報
    """
    user_id: str
    channel_id: str
    project_ids: List[str]
    mentioned_users: List[str] = None
    mentioned_projects: List[str] = None


class QueryServiceError(Exception):
    """
    クエリサービス関連のエラー
    """
    pass


class QueryService:
    """
    自然言語クエリを処理するサービス
    """
    def __init__(self):
        """
        設定を読み込み、AIクライアントを初期化
        """
        self.settings = get_settings()
        self.ai_provider = self.settings.ai_provider
        self.ai_model = self.settings.ai_model
        self.ai_api_key = self.settings.ai_api_key
        
        # AIプロバイダに応じてクライアントを初期化
        if self.ai_provider == "gemini":
            genai.configure(api_key=self.ai_api_key)
            self.model = genai.GenerativeModel(self.ai_model)
        elif self.ai_provider == "bedrock":
            self.bedrock_client = boto3.client(
                service_name="bedrock-runtime",
                region_name="us-east-1"  # 適切なリージョンに変更
            )
        else:
            raise QueryServiceError(f"未対応のAIプロバイダ: {self.ai_provider}")
            
        # クエリ意図の正規表現パターン
        self.intent_patterns = {
            QueryIntent.TASKS_DUE_TODAY: [
                r"今日(\s|の|に|は|が|)*(タスク|課題|作業|やること)",
                r"本日(\s|の|に|は|が|)*(タスク|課題|作業|やること)",
                r"today('s)*\s*(tasks|issues)"
            ],
            QueryIntent.TASKS_DUE_THIS_WEEK: [
                r"今週(\s|の|に|は|が|中|)*(タスク|課題|作業|やること)",
                r"今週中(\s|の|に|は|が|)*(タスク|課題|作業|やること)",
                r"this\s*week('s)*\s*(tasks|issues)"
            ],
            QueryIntent.TASKS_OVERDUE: [
                r"(期限|締め切り)(\s|が|は|)*切れ",
                r"遅延(\s|した|している|の|)*(タスク|課題|作業)",
                r"overdue\s*(tasks|issues)"
            ],
            QueryIntent.TASKS_BY_ASSIGNEE: [
                r"<@[A-Z0-9]+>(\s|の|が|担当|)*(タスク|課題|作業)",
                r"(誰|だれ)(\s|が|の|)*(タスク|課題|作業)",
                r"(担当者|アサイン)(\s|が|の|は|)*(タスク|課題|作業)"
            ],
            QueryIntent.PROJECT_STATUS: [
                r"(プロジェクト|案件)(\s|の|)*(状況|ステータス|進捗|状態)",
                r"(全体|ぜんたい)(\s|の|)*(状況|ステータス|進捗|状態)",
                r"project\s*status"
            ]
        }
    
    def extract_query_intent(self, query: str) -> QueryIntent:
        """
        クエリから意図を抽出
        
        Args:
            query: ユーザーからのクエリ文字列
            
        Returns:
            クエリの意図
        """
        # 小文字に変換して比較
        query_lower = query.lower()
        
        for intent, patterns in self.intent_patterns.items():
            for pattern in patterns:
                if re.search(pattern, query_lower):
                    logger.info(f"クエリ '{query}' から意図を抽出: {intent.name}")
                    return intent
                    
        logger.info(f"クエリ '{query}' から意図を抽出できませんでした")
        return QueryIntent.UNKNOWN
    
    def extract_mentioned_users(self, query: str) -> List[str]:
        """
        クエリからメンションされたユーザーを抽出
        
        Args:
            query: ユーザーからのクエリ文字列
            
        Returns:
            メンションされたユーザーIDのリスト
        """
        # Slackのユーザーメンションパターン: <@U12345>
        pattern = r"<@([A-Z0-9]+)>"
        matches = re.findall(pattern, query)
        return matches
    
    def process_natural_language_query(self, query: str, context: QueryContext) -> str:
        """
        自然言語クエリを処理して回答を生成
        
        Args:
            query: ユーザーからのクエリ文字列
            context: クエリのコンテキスト情報
            
        Returns:
            生成された回答
        """
        try:
            # クエリの意図を抽出
            intent = self.extract_query_intent(query)
            
            # メンションされたユーザーを抽出
            mentioned_users = self.extract_mentioned_users(query)
            if mentioned_users:
                context.mentioned_users = mentioned_users
                
            # 意図に応じた処理
            if intent == QueryIntent.UNKNOWN:
                # 意図が不明な場合はAIに処理を委譲
                return self._generate_ai_response(query, context)
            else:
                # 意図に応じた構造化された回答を生成
                # 実際のタスクデータは後で実装するTaskServiceから取得
                return self._generate_structured_response(query, intent, context)
                
        except Exception as e:
            logger.error(f"クエリ処理中にエラーが発生しました: {str(e)}")
            return f"申し訳ありません、クエリの処理中にエラーが発生しました。もう一度お試しください。\nエラー: {str(e)}"
    
    def _generate_structured_response(self, query: str, intent: QueryIntent, context: QueryContext) -> str:
        """
        意図に応じた構造化された回答を生成
        
        Args:
            query: ユーザーからのクエリ文字列
            intent: 抽出された意図
            context: クエリのコンテキスト情報
            
        Returns:
            生成された回答
        """
        # TaskServiceを初期化
        from taco.services.task_service import TaskService
        task_service = TaskService()
        
        try:
            if intent == QueryIntent.TASKS_DUE_TODAY:
                # 今日期限のタスクを取得
                tasks = task_service.get_tasks_due_today()
                return self.format_task_response(tasks, intent)
                
            elif intent == QueryIntent.TASKS_DUE_THIS_WEEK:
                # 今週期限のタスクを取得
                tasks = task_service.get_tasks_due_this_week()
                return self.format_task_response(tasks, intent)
                
            elif intent == QueryIntent.TASKS_OVERDUE:
                # 期限切れのタスクを取得
                tasks = task_service.get_overdue_tasks()
                return self.format_task_response(tasks, intent)
                
            elif intent == QueryIntent.TASKS_BY_ASSIGNEE:
                # 特定のユーザーのタスクを取得
                if context.mentioned_users:
                    # BacklogユーザーIDとSlackユーザーIDのマッピングが必要
                    # 簡易的な実装として、すべてのタスクを取得して担当者でフィルタリング
                    all_tasks = task_service.get_all_tasks()
                    tasks = []
                    
                    # メンションされたユーザーの担当タスクを抽出
                    # 注: 実際の実装では、SlackユーザーIDからBacklogユーザーIDへの変換が必要
                    user_mentions = ", ".join([f"<@{user}>" for user in context.mentioned_users])
                    return f"{user_mentions} の担当タスクは以下の通りです：\n" + \
                           "（注: SlackユーザーとBacklogユーザーのマッピングが未実装のため、正確な情報ではありません）\n" + \
                           "・タスク情報を取得するには、Backlogユーザー名で質問してください"
                else:
                    return "担当者が指定されていません。@ユーザー名 を含めて質問してください。"
                    
            elif intent == QueryIntent.PROJECT_STATUS:
                # プロジェクト全体の状況を取得
                overdue_tasks = task_service.get_overdue_tasks()
                due_today_tasks = task_service.get_tasks_due_today()
                due_this_week_tasks = task_service.get_tasks_due_this_week()
                completion_rate = task_service.get_completion_rate()
                
                status_text = f"プロジェクト全体の状況：\n"
                status_text += f"・完了率: {completion_rate:.1f}%\n"
                status_text += f"・期限切れタスク: {len(overdue_tasks)}件\n"
                status_text += f"・今日期限タスク: {len(due_today_tasks)}件\n"
                status_text += f"・今週期限タスク: {len(due_this_week_tasks)}件\n"
                
                return status_text
                
            else:
                return "申し訳ありません、その質問にはお答えできません。別の質問をお試しください。"
                
        except Exception as e:
            logger.error(f"構造化応答の生成中にエラーが発生しました: {str(e)}")
            return f"申し訳ありません、タスク情報の取得中にエラーが発生しました。\nエラー: {str(e)}"
    
    def _generate_ai_response(self, query: str, context: QueryContext) -> str:
        """
        AIを使用して回答を生成
        
        Args:
            query: ユーザーからのクエリ文字列
            context: クエリのコンテキスト情報
            
        Returns:
            生成された回答
        """
        try:
            if self.ai_provider == "gemini":
                return self._generate_gemini_response(query, context)
            elif self.ai_provider == "bedrock":
                return self._generate_bedrock_response(query, context)
            else:
                raise QueryServiceError(f"未対応のAIプロバイダ: {self.ai_provider}")
        except Exception as e:
            logger.error(f"AI応答生成中にエラーが発生しました: {str(e)}")
            return "申し訳ありません、回答の生成中にエラーが発生しました。以下のような質問を試してみてください：\n・今日のタスクは？\n・今週の期限切れタスクは？\n・プロジェクト全体の状況は？"
    
    def _generate_gemini_response(self, query: str, context: QueryContext) -> str:
        """
        Gemini APIを使用して回答を生成
        
        Args:
            query: ユーザーからのクエリ文字列
            context: クエリのコンテキスト情報
            
        Returns:
            生成された回答
        """
        system_prompt = """
        あなたはプロジェクト管理アシスタントのTACO（Task & Communication Optimizer）です。
        Backlogのタスク情報とSlackのコミュニケーションを統合して、プロジェクト管理をサポートします。
        
        以下のような質問に簡潔に回答してください：
        - タスクの期限や状況に関する質問
        - プロジェクト全体の進捗状況
        - 特定の担当者のタスク
        
        回答は簡潔かつ具体的に、Slack形式で整形してください。
        """
        
        try:
            response = self.model.generate_content(
                [system_prompt, query]
            )
            
            if response.text:
                return response.text
            else:
                return "申し訳ありません、回答を生成できませんでした。別の質問をお試しください。"
                
        except Exception as e:
            logger.error(f"Gemini API呼び出し中にエラーが発生しました: {str(e)}")
            raise
    
    def _generate_bedrock_response(self, query: str, context: QueryContext) -> str:
        """
        Amazon Bedrockを使用して回答を生成
        
        Args:
            query: ユーザーからのクエリ文字列
            context: クエリのコンテキスト情報
            
        Returns:
            生成された回答
        """
        system_prompt = """
        あなたはプロジェクト管理アシスタントのTACO（Task & Communication Optimizer）です。
        Backlogのタスク情報とSlackのコミュニケーションを統合して、プロジェクト管理をサポートします。
        
        以下のような質問に簡潔に回答してください：
        - タスクの期限や状況に関する質問
        - プロジェクト全体の進捗状況
        - 特定の担当者のタスク
        
        回答は簡潔かつ具体的に、Slack形式で整形してください。
        """
        
        try:
            # モデルに応じてリクエスト形式を変更
            if "claude" in self.ai_model:
                # Anthropic Claude用のリクエスト形式
                request_body = {
                    "prompt": f"\n\nHuman: {system_prompt}\n\n{query}\n\nAssistant:",
                    "max_tokens_to_sample": 1000,
                    "temperature": 0.7,
                    "top_p": 0.9,
                }
                
                response = self.bedrock_client.invoke_model(
                    modelId=self.ai_model,
                    body=json.dumps(request_body)
                )
                
                response_body = json.loads(response.get("body").read())
                return response_body.get("completion", "")
                
            else:
                # その他のモデル用（汎用的な形式）
                request_body = {
                    "inputText": f"{system_prompt}\n\nユーザー: {query}",
                    "textGenerationConfig": {
                        "maxTokenCount": 1000,
                        "temperature": 0.7,
                        "topP": 0.9,
                    }
                }
                
                response = self.bedrock_client.invoke_model(
                    modelId=self.ai_model,
                    body=json.dumps(request_body)
                )
                
                response_body = json.loads(response.get("body").read())
                return response_body.get("results", [{}])[0].get("outputText", "")
                
        except Exception as e:
            logger.error(f"Bedrock API呼び出し中にエラーが発生しました: {str(e)}")
            raise
    
    def format_task_response(self, tasks: List[Task], intent: QueryIntent) -> str:
        """
        タスクリストを整形して回答を生成
        
        Args:
            tasks: タスクのリスト
            intent: クエリの意図
            
        Returns:
            整形された回答
        """
        if not tasks:
            return "該当するタスクはありません。"
            
        # 意図に応じたヘッダーを設定
        if intent == QueryIntent.TASKS_DUE_TODAY:
            header = "📅 *今日期限のタスク*\n"
        elif intent == QueryIntent.TASKS_DUE_THIS_WEEK:
            header = "📆 *今週期限のタスク*\n"
        elif intent == QueryIntent.TASKS_OVERDUE:
            header = "⚠️ *期限切れのタスク*\n"
        elif intent == QueryIntent.TASKS_BY_ASSIGNEE:
            header = "👤 *担当者のタスク*\n"
        else:
            header = "📋 *タスク一覧*\n"
            
        # タスクリストを整形
        task_lines = []
        for task in tasks:
            due_date_str = task.due_date.strftime("%Y/%m/%d") if task.due_date else "期限なし"
            status_emoji = "🔴" if task.is_overdue else "🟡" if task.is_due_today else "🟢"
            
            task_line = f"{status_emoji} <https://{self.settings.backlog_space_key}.backlog.com/view/{task.id}|{task.id}> "
            task_line += f"*{task.summary}*"
            task_line += f" (期限: {due_date_str}, 状態: {task.status.value})"
            
            task_lines.append(task_line)
            
        # 回答を組み立て
        response = header + "\n".join(task_lines)
        
        # フッターを追加
        response += f"\n\n合計: {len(tasks)}件のタスク"
        
        return response
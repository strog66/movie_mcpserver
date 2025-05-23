from typing import Any, List, Dict, Optional
import asyncio
import json
import os
from datetime import datetime
from fastmcp import FastMCP
import requests
from bs4 import BeautifulSoup
import time
from functools import wraps

# 初始化 FastMCP 服务器
mcp = FastMCP("movie_mcp")

# 全局变量
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

# 确保目录存在
os.makedirs(DATA_DIR, exist_ok=True)

# 常量定义
DOUBAN_API = "https://movie.douban.com/j/subject_suggest?q={keyword}"
DOUBAN_DETAIL = "https://movie.douban.com/subject/{id}/"
DOUBAN_COMMENTS = "https://movie.douban.com/subject/{id}/comments"
MAX_RETRIES = 3
RETRY_DELAY = 2

def retry_on_failure(max_retries=MAX_RETRIES, delay=RETRY_DELAY):
    """重试装饰器"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            for i in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if i == max_retries - 1:
                        raise e
                    print(f"尝试 {i+1}/{max_retries} 失败: {str(e)}")
                    await asyncio.sleep(delay)
            return None
        return wrapper
    return decorator

def save_to_json(data: dict, filename: str):
    """保存数据到JSON文件"""
    filepath = os.path.join(DATA_DIR, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_from_json(filename: str) -> dict:
    """从JSON文件加载数据"""
    filepath = os.path.join(DATA_DIR, filename)
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

@mcp.tool()
async def search_movies(keyword: str, limit: int = 5) -> str:
    """搜索电影信息
    
    Args:
        keyword: 搜索关键词
        limit: 返回结果数量限制
    """
    try:
        print(f"开始搜索电影: {keyword}")
        resp = requests.get(
            DOUBAN_API.format(keyword=keyword),
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10
        )
        resp.raise_for_status()
        
        results = []
        data = resp.json()
        print(f"获取到搜索结果: {data}")
        
        for item in data[:limit]:
            results.append({
                "title": item["title"],
                "year": item.get("year", ""),
                "douban_id": item["id"],
                "subtitle": item.get("sub_title", ""),
                "type": item.get("type", "movie")
            })
        
        # 格式化返回结果
        if results:
            result = "搜索结果：\n\n"
            for i, movie in enumerate(results, 1):
                result += f"{i}. {movie['title']} ({movie.get('year', '未知年份')})\n"
                result += f"   ID: {movie['douban_id']}\n"
                if movie.get('subtitle'):
                    result += f"   副标题: {movie['subtitle']}\n"
                result += "\n"
            return result
        else:
            return f"未找到与\"{keyword}\"相关的电影"
    
    except Exception as e:
        return f"搜索电影时出错: {str(e)}"

@mcp.tool()
async def get_movie_detail(douban_id: str) -> str:
    """获取电影详细信息
    
    Args:
        douban_id: 豆瓣电影ID
    """
    try:
        url = DOUBAN_DETAIL.format(id=douban_id)
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, "html.parser")
        
        info = {
            "douban_id": douban_id,
            "title": soup.select_one("h1 span").get_text(strip=True) if soup.select_one("h1 span") else "未知标题",
            "rating": soup.select_one(".rating_num").get_text(strip=True) if soup.select_one(".rating_num") else "无评分",
            "votes": soup.select_one(".rating_people span").get_text(strip=True) if soup.select_one(".rating_people span") else "0",
        }
        
        # 获取基本信息
        info_section = soup.find(id="info")
        if info_section:
            for item in info_section.get_text().split("\n"):
                item = item.strip()
                if ":" in item:
                    key, value = item.split(":", 1)
                    key = key.strip()
                    value = value.strip()
                    if key and value:
                        info[key] = value
        
        # 获取类型信息
        genres = soup.find_all("span", property="v:genre")
        if genres:
            info["类型"] = " / ".join([g.get_text(strip=True) for g in genres])
        
        # 获取简介
        summary = soup.find(property="v:summary")
        if summary:
            info["简介"] = summary.get_text(strip=True)
        else:
            info["简介"] = "无简介"
        
        # 获取海报
        poster = soup.select_one("#mainpic img")
        info["海报链接"] = poster["src"] if poster else None
        
        # 格式化返回结果
        result = f"电影详情：\n\n"
        result += f"标题: {info['title']}\n"
        result += f"评分: {info['rating']} ({info['votes']}人评价)\n"
        for key, value in info.items():
            if key not in ['title', 'rating', 'votes', 'douban_id']:
                result += f"{key}: {value}\n"
        
        return result
    
    except Exception as e:
        return f"获取电影详情时出错: {str(e)}"

@mcp.tool()
async def analyze_movie(douban_id: str) -> dict:
    """分析电影信息，返回详细信息供AI生成评论
    
    Args:
        douban_id: 豆瓣电影ID
    """
    try:
        # 获取电影详情
        detail_result = await get_movie_detail(douban_id)
        
        # 解析获取到的电影信息
        info = {}
        for line in detail_result.split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                info[key.strip()] = value.strip()
        
        # 分析电影类型和主题
        genres = info.get('类型', '').split(' / ')
        themes = []
        
        # 根据类型推断主题
        genre_themes = {
            '剧情': ['故事性', '人物塑造', '情节发展'],
            '喜剧': ['幽默感', '笑点', '欢乐氛围'],
            '动作': ['动作场面', '视觉效果', '刺激感'],
            '爱情': ['感情线', '浪漫元素', '人物关系'],
            '科幻': ['科技元素', '未来世界', '想象力'],
            '动画': ['动画效果', '角色设计', '视觉风格'],
            '悬疑': ['推理元素', '剧情转折', '悬念设置'],
            '惊悚': ['紧张氛围', '恐怖元素', '心理描写'],
            '恐怖': ['恐怖氛围', '惊吓元素', '心理恐惧'],
            '犯罪': ['犯罪元素', '社会问题', '人性探讨'],
            '奇幻': ['奇幻元素', '想象力', '世界观'],
            '冒险': ['冒险元素', '探索精神', '刺激感'],
            '灾难': ['灾难场景', '人性考验', '生存主题'],
            '音乐': ['音乐元素', '艺术表现', '情感表达'],
            '历史': ['历史背景', '时代特征', '文化内涵'],
            '战争': ['战争场面', '历史背景', '人性探讨'],
            '传记': ['人物生平', '历史背景', '人物塑造'],
            '运动': ['体育精神', '竞技元素', '团队合作'],
            '纪录片': ['真实记录', '社会观察', '知识普及']
        }
        
        for genre in genres:
            if genre in genre_themes:
                themes.extend(genre_themes[genre])
        
        # 返回分析结果
        return {
            "douban_id": douban_id,
            "基本信息": info,
            "类型": genres,
            "主题": list(set(themes)),  # 去重
            "评分": info.get('评分', '无评分'),
            "评价人数": info.get('评价人数', '0'),
            "message": "请根据电影信息生成一条专业的影评，注意以下要点：\n1. 分析电影的类型特点和主题表现\n2. 评价演员表演和导演手法\n3. 讨论电影的社会意义和艺术价值\n4. 给出客观的评分建议"
        }
    
    except Exception as e:
        return {"error": f"分析电影信息时出错: {str(e)}"}

@mcp.tool()
async def get_movie_comments(douban_id: str, limit: int = 5) -> str:
    """获取电影评论
    
    Args:
        douban_id: 豆瓣电影ID
        limit: 返回评论数量限制
    """
    try:
        url = DOUBAN_COMMENTS.format(id=douban_id)
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, "html.parser")
        comments = []
        
        # 获取评论列表
        comment_items = soup.select(".comment-item")
        for item in comment_items[:limit]:
            try:
                author = item.select_one(".comment-info a").get_text(strip=True)
                rating = item.select_one(".rating")
                rating = rating["class"][0][-2] if rating else "无评分"
                content = item.select_one(".comment-content").get_text(strip=True)
                time = item.select_one(".comment-time").get_text(strip=True)
                
                comments.append({
                    "作者": author,
                    "评分": rating,
                    "内容": content,
                    "时间": time
                })
            except Exception as e:
                print(f"解析评论出错: {str(e)}")
                continue
        
        # 格式化返回结果
        if comments:
            result = f"电影评论：\n\n"
            for i, comment in enumerate(comments, 1):
                result += f"{i}. {comment['作者']} (评分: {comment['评分']})\n"
                result += f"   时间: {comment['时间']}\n"
                result += f"   内容: {comment['内容']}\n\n"
            return result
        else:
            return "未找到任何评论"
    
    except Exception as e:
        return f"获取电影评论时出错: {str(e)}"

@mcp.tool()
async def get_movie_recommendations(douban_id: str, limit: int = 5) -> str:
    """获取电影推荐
    
    Args:
        douban_id: 豆瓣电影ID
        limit: 返回推荐数量限制
    """
    try:
        url = DOUBAN_DETAIL.format(id=douban_id)
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, "html.parser")
        recommendations = []
        
        # 获取推荐电影列表
        rec_items = soup.select(".recommendations-bd dl")
        for item in rec_items[:limit]:
            try:
                title = item.select_one("a").get_text(strip=True)
                link = item.select_one("a")["href"]
                rec_id = link.split("/")[-2]
                rating = item.select_one(".rating_nums")
                rating = rating.get_text(strip=True) if rating else "无评分"
                
                recommendations.append({
                    "title": title,
                    "douban_id": rec_id,
                    "rating": rating
                })
            except Exception as e:
                print(f"解析推荐电影出错: {str(e)}")
                continue
        
        # 格式化返回结果
        if recommendations:
            result = f"推荐电影：\n\n"
            for i, movie in enumerate(recommendations, 1):
                result += f"{i}. {movie['title']}\n"
                result += f"   评分: {movie['rating']}\n"
                result += f"   ID: {movie['douban_id']}\n\n"
            return result
        else:
            return "未找到任何推荐电影"
    
    except Exception as e:
        return f"获取电影推荐时出错: {str(e)}"

@mcp.tool()
async def save_movie_info(douban_id: str) -> str:
    """保存电影信息到本地
    
    Args:
        douban_id: 豆瓣电影ID
    """
    try:
        # 获取电影详情
        detail_result = await get_movie_detail(douban_id)
        
        # 解析电影信息
        info = {}
        for line in detail_result.split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                info[key.strip()] = value.strip()
        
        # 获取评论
        comments_result = await get_movie_comments(douban_id)
        
        # 获取推荐
        recommendations_result = await get_movie_recommendations(douban_id)
        
        # 整合所有信息
        movie_data = {
            "基本信息": info,
            "评论": comments_result,
            "推荐": recommendations_result,
            "保存时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # 保存到文件
        filename = f"movie_{douban_id}_{TIMESTAMP}.json"
        save_to_json(movie_data, filename)
        
        return f"电影信息已保存到文件: {filename}"
    
    except Exception as e:
        return f"保存电影信息时出错: {str(e)}"

if __name__ == "__main__":
    # 初始化并运行服务器
    print("启动电影查询MCP服务器...")
    print("请在MCP客户端（如Claude for Desktop）中配置此服务器")
    mcp.run(transport='stdio') 
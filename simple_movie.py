import asyncio
import requests
from bs4 import BeautifulSoup
import time
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 常量定义
DOUBAN_API = "https://movie.douban.com/j/subject_suggest?q={keyword}"
DOUBAN_DETAIL = "https://movie.douban.com/subject/{id}/"
IMDB_SEARCH = "https://www.imdb.com/find?q={keyword}&s=tt"

async def search_movies(keyword: str, limit: int = 5):
    """搜索电影信息"""
    try:
        logger.info(f"开始搜索电影: {keyword}")
        resp = requests.get(
            DOUBAN_API.format(keyword=keyword),
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10
        )
        resp.raise_for_status()
        
        results = []
        data = resp.json()
        logger.info(f"获取到搜索结果: {data}")
        
        for item in data[:limit]:
            results.append({
                "title": item["title"],
                "year": item.get("year", ""),
                "douban_id": item["id"],
                "subtitle": item.get("sub_title", ""),
                "type": item.get("type", "movie")
            })
        return results
    except Exception as e:
        logger.error(f"搜索电影时出错: {e}")
        return []

async def get_movie_detail(douban_id: str):
    """获取电影详细信息"""
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
            # 获取所有基本信息项
            for item in info_section.get_text().split("\n"):
                item = item.strip()
                if ":" in item:
                    key, value = item.split(":", 1)
                    key = key.strip()
                    value = value.strip()
                    if key and value:
                        info[key] = value
            
            # 特殊处理导演、编剧、主演（因为这些可能有多个值）
            for role in ["导演", "编剧", "主演"]:
                role_span = info_section.find("span", string=role)
                if role_span:
                    next_span = role_span.find_next_sibling("span")
                    if next_span and next_span.get("class") == ["attrs"]:
                        names = [a.get_text(strip=True) for a in next_span.find_all("a")]
                        info[role] = " / ".join(names)
        
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
        
        # 打印调试信息
        logger.info(f"获取到的电影信息: {info}")
        
        return info
    except Exception as e:
        logger.error(f"获取电影详情时出错: {e}")
        return {"error": str(e)}
async def analyze_rating(rating: str):
    """分析电影评分"""
    try:
        score = float(rating)
        if score >= 8.5:
            return {
                "level": "优秀",
                "description": "这是一部非常优秀的电影，强烈推荐观看",
                "score": score
            }
        elif score >= 7.0:
            return {
                "level": "良好",
                "description": "这是一部不错的电影，值得一看",
                "score": score
            }
        elif score >= 5.0:
            return {
                "level": "一般",
                "description": "这是一部普通的电影，可以看看",
                "score": score
            }
        else:
            return {
                "level": "较差",
                "description": "这部电影评分较低，建议谨慎观看",
                "score": score
            }
    except ValueError:
        return {
            "level": "无法评估",
            "description": "评分数据无效",
            "score": None
        }

async def recommend_similar(title: str, limit: int = 5):
    """推荐相似电影"""
    try:
        url = IMDB_SEARCH.format(keyword=title)
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, "html.parser")
        
        results = []
        similar_section = soup.find("section", {"data-testid": "find-more-like-this"})
        if similar_section:
            for item in similar_section.find_all("li")[:limit]:
                title_tag = item.find("a")
                if title_tag:
                    results.append({
                        "title": title_tag.get_text(strip=True),
                        "url": "https://www.imdb.com" + title_tag["href"],
                        "source": "IMDB"
                    })
        return results
    except Exception as e:
        logger.error(f"获取相似电影时出错: {e}")
        return []

async def main():
    print("欢迎使用电影信息查询系统！")
    
    while True:
        print("\n=== 电影信息查询系统 ===")
        print("1. 搜索电影")
        print("2. 获取电影详情")
        print("3. 分析评分")
        print("4. 推荐相似电影")
        print("0. 退出")
        print("=====================")
        2
        
        choice = input("请选择功能 (0-4): ")
        
        if choice == "0":
            print("感谢使用，再见！")
            break
            
        elif choice == "1":
            keyword = input("请输入要搜索的电影名称: ")
            print("\n搜索中...")
            try:
                results = await search_movies(keyword)
                if results:
                    print("\n搜索结果:")
                    for movie in results:
                        print(f"- {movie['title']} ({movie.get('year', '未知年份')})")
                        print(f"  ID: {movie['douban_id']}")
                        if movie.get('subtitle'):
                            print(f"  副标题: {movie['subtitle']}")
                        print()
                else:
                    print("未找到相关电影")
            except Exception as e:
                print(f"搜索出错: {e}")
            
        elif choice == "2":
            movie_id = input("请输入豆瓣电影ID: ")
            print("\n获取详情中...")
            try:
                details = await get_movie_detail(movie_id)
                if details and "error" not in details:
                    print("\n电影详情:")
                    for key, value in details.items():
                        print(f"{key}: {value}")
                else:
                    print("获取电影详情失败")
            except Exception as e:
                print(f"获取详情出错: {e}")
            
        elif choice == "3":
            rating = input("请输入评分 (0-10): ")
            print("\n分析评分中...")
            try:
                analysis = await analyze_rating(rating)
                print("\n评分分析:")
                for key, value in analysis.items():
                    print(f"{key}: {value}")
            except Exception as e:
                print(f"分析评分出错: {e}")
            
        elif choice == "4":
            title = input("请输入电影名称: ")
            print("\n获取推荐中...")
            try:
                similar = await recommend_similar(title)
                if similar:
                    print("\n相似电影:")
                    for movie in similar:
                        print(f"- {movie['title']}")
                        print(f"  链接: {movie['url']}")
                        print()
                else:
                    print("未找到相似电影")
            except Exception as e:
                print(f"获取推荐出错: {e}")
            
        else:
            print("无效的选择，请重试")
        
        input("\n按回车键继续...")

if __name__ == "__main__":
    asyncio.run(main()) 
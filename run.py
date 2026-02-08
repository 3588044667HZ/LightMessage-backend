import asyncio
import logging

from router import server

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """主函数"""
    # 创建服务器实例
    # 启动服务器
    try:
        await server.initialize()
        await server.start()
    except KeyboardInterrupt:
        logger.info("接收到中断信号，正在关闭服务器...")
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())

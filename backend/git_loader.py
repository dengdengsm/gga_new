import os
import subprocess
import shutil
import logging
from typing import Dict, List, Set

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class GitHubLoader:
    def __init__(self, base_dir: str = "./.Project"):
        """
        初始化加载器
        :param base_dir: 项目存放的基础目录，默认为当前目录下的 .Project 文件夹
        """
        self.base_dir = os.path.abspath(base_dir)
        if not os.path.exists(self.base_dir):
            os.makedirs(self.base_dir)

    def _get_repo_name(self, repo_url: str) -> str:
        """从 URL 中提取仓库名称"""
        return repo_url.rstrip('/').split('/')[-1].replace('.git', '')

    def clone_repo(self, repo_url: str, force_update: bool = True) -> str:
        """
        拉取 GitHub 仓库
        :param repo_url: GitHub 仓库地址
        :param force_update: 如果目录存在，是否强制删除重新克隆
        :return: 本地仓库的绝对路径
        """
        repo_name = self._get_repo_name(repo_url)
        target_path = os.path.join(self.base_dir, repo_name)

        if os.path.exists(target_path):
            if force_update:
                logger.info(f"目录已存在，正在清理旧文件: {target_path}")
                shutil.rmtree(target_path, ignore_errors=True)
            else:
                logger.info(f"目录已存在，跳过克隆: {target_path}")
                return target_path

        logger.info(f"正在克隆仓库 {repo_url} 到 {target_path} ...")
        try:
            # 使用系统 git 命令，避免依赖 heavy 的 gitpython 库
            subprocess.run(
                ["git", "clone", "--depth", "1", repo_url, target_path],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            logger.info("克隆完成。")
        except subprocess.CalledProcessError as e:
            logger.error(f"Git 克隆失败: {e}")
            raise RuntimeError(f"无法克隆仓库: {repo_url}")
        
        return target_path

    def classify_files(self, repo_path: str) -> Dict[str, List[str]]:
        """
        遍历仓库文件并进行分类
        :param repo_path: 仓库本地路径
        :return: 包含分类路径列表的字典
        """
        classified_files = {
            "documentation": [], # 介绍性文件
            "configuration": [], # 配置文件
            "source_code": [],   # 核心代码
            "others": []         # 其他资源(图片等)
        }

        # 定义分类规则 (后缀名)
        ext_rules = {
            "source_code": {
                '.py', '.java', '.c', '.cpp', '.h', '.hpp', '.cs', '.go', '.rs', 
                '.js', '.jsx', '.ts', '.tsx', '.php', '.rb', '.swift', '.kt', 
                '.scala', '.lua', '.pl', '.sh', '.bat'
            },
            "configuration": {
                '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf', 
                '.env', '.gitignore', '.dockerignore', '.xml', '.gradle', 
                '.properties', '.cmake'
            },
            "documentation": {
                '.md', '.markdown', '.rst', '.txt', '.pdf', '.doc', '.docx'
            }
        }

        # 定义特定文件名规则 (优先级高于后缀)
        filename_rules = {
            "configuration": {
                'dockerfile', 'makefile', 'cmakelists.txt', 'requirements.txt', 
                'package.json', 'tsconfig.json', 'pom.xml', 'setup.py', 'go.mod', 'go.sum'
            },
            "documentation": {
                'readme', 'license', 'contributing', 'changelog', 'authors', 'faq', 'notice'
            }
        }

        # 需要忽略的目录
        ignore_dirs = {'.git', '__pycache__', 'node_modules', 'venv', '.idea', '.vscode', 'dist', 'build'}

        for root, dirs, files in os.walk(repo_path):
            # 修改 dirs 列表以跳过忽略的目录
            dirs[:] = [d for d in dirs if d not in ignore_dirs]

            for file in files:
                file_path = os.path.join(root, file)
                file_lower = file.lower()
                filename_no_ext = os.path.splitext(file_lower)[0]
                _, ext = os.path.splitext(file_lower)

                is_classified = False

                # 1. 优先检查特定文件名
                if file_lower in filename_rules['configuration'] or (file_lower == 'setup.py'):
                    # 特殊处理：setup.py 虽然是 py 文件，但在项目中通常归为配置
                    classified_files['configuration'].append(file_path)
                    is_classified = True
                
                # 检查文件名是否包含 readme 等关键词
                elif any(key in filename_no_ext for key in filename_rules['documentation']):
                    classified_files['documentation'].append(file_path)
                    is_classified = True
                
                # 2. 检查后缀名
                if not is_classified:
                    if ext in ext_rules['source_code']:
                        classified_files['source_code'].append(file_path)
                    elif ext in ext_rules['configuration']:
                        classified_files['configuration'].append(file_path)
                    elif ext in ext_rules['documentation']:
                        classified_files['documentation'].append(file_path)
                    else:
                        classified_files['others'].append(file_path)

        # 统计输出
        logger.info(f"文件分类完成: "
                    f"代码({len(classified_files['source_code'])}), "
                    f"配置({len(classified_files['configuration'])}), "
                    f"文档({len(classified_files['documentation'])})")
        
        return classified_files

# --- 使用示例 ---
if __name__ == "__main__":
    # 示例：拉取 requests 库进行分析
    loader = GitHubLoader()
    try:
        url = "https://github.com/OpenBMB/ChatDev.git" 
        local_path = loader.clone_repo(url)
        print(f"仓库路径: {local_path}")
        
        files_map = loader.classify_files(local_path)
        
        print("\n--- 核心代码文件 (前5个) ---")
        for f in files_map['source_code'][:5]:
            print(f)
            
        print("\n--- 配置文件 (前5个) ---")
        for f in files_map['configuration'][:5]:
            print(f)

    except Exception as e:
        print(f"发生错误: {e}")
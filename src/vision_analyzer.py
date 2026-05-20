import base64


class VisionAnalyzer:
    def __init__(self):
        pass

    def analyze_image(self, image_path):
        """
        分析图片，返回 base64 编码供 Hermes 使用
        """
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def analyze_screenshot(self, image_path):
        """
        特别用于分析报错截图
        """
        return self.analyze_image(image_path)

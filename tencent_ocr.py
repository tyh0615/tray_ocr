import base64
import datetime as _dt
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hmac_sha256(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


@dataclass
class TencentOcrConfig:
    endpoint: str
    region: str
    secret_id: str
    secret_key: str
    multi_language: bool = False  # True=ConfigID=MulOCR；False=ConfigID=OCR
    action: str = "GeneralAccurateOCR"  # 调用的接口 Action


# OCR 接口分类目录：(分类名, [(Action, 中文名), ...])
# 全部走统一的 Version 2018-11-19（腾讯云 OCR 产品线统一版本）
OCR_ACTION_CATALOG = [
    ("通用文字识别", [
        ("GeneralBasicOCR", "通用印刷体识别"),
        ("GeneralAccurateOCR", "通用文字识别（高精度版）"),
        ("RecognizeTableAccurateOCR", "表格识别（V3）"),
        ("ClassifyStoreName", "商户照片分类"),
        ("RecognizeStoreName", "商户门头照识别"),
        ("AdvertiseOCR", "广告文字识别"),
        ("RecognizeAgent", "通用文字识别Agent"),
        ("SealOCR", "印章识别"),
    ]),
    ("卡证文字识别", [
        ("RecognizeValidIDCardOCR", "有效身份证件识别（鉴伪版）"),
        ("IDCardOCR", "身份证识别"),
        ("BankCardOCR", "银行卡识别"),
        ("VehicleLicenseOCR", "行驶证识别"),
        ("DriverLicenseOCR", "驾驶证识别"),
        ("RecognizeEncryptedIDCardOCR", "身份证识别（安全加密版）"),
        ("BizLicenseOCR", "营业执照识别"),
        ("BusinessCardOCR", "名片识别"),
        ("VehicleRegCertOCR", "机动车登记证书识别"),
        ("ClassifyDetectOCR", "智能卡证分类"),
        ("MLIDPassportOCR", "护照识别（多国多地区护照）"),
        ("MainlandPermitOCR", "港澳台通行证及来往内地通行证识别"),
        ("HKIDCardOCR", "中国香港身份证识别"),
    ]),
    ("票据单据识别", [
        ("RecognizeGeneralInvoice", "通用票据识别（高级版）"),
        ("VatInvoiceVerifyNew", "增值税发票核验（新版）"),
        ("VatInvoiceOCR", "增值税发票识别"),
        ("VerifyOfdVatInvoiceOCR", "OFD发票识别"),
        ("BankSlipOCR", "银行回单识别"),
        ("RecognizeMedicalInvoiceOCR", "医疗票据识别"),
    ]),
    ("文档智能", [
        ("ExtractDocBasic", "文档抽取（基础版）"),
        ("ExtractDocMulti", "文档抽取（多模态版）"),
        ("ExtractDocAgent", "实时文档抽取Agent"),
        ("DescribeExtractDocAgentJob", "异步文档抽取Agent(查询任务)"),
        ("SubmitExtractDocAgentJob", "异步文档抽取Agent(创建任务)"),
        ("MultimodalDocParse", "多模态解析（文档版）"),
        ("SubmitQuestionMarkAgentJob", "试题批改Agent（提交任务）"),
        ("DescribeQuestionMarkAgentJob", "试题批改Agent（查询任务）"),
        ("CropEnhanceImageOCR", "图像切边增强"),
        ("EraseHandwrittenImageOCR", "试卷手写擦除"),
        ("QuestionSplitOCR", "试卷切题"),
        ("QuestionSplitLayoutOCR", "试卷切题（仅检测）"),
        ("HandwritingEssayOCR", "中英文手写作文识别"),
        ("SubmitMarkEssayAgentJob", "作文批改Agent（提交任务）"),
        ("DescribeMarkEssayAgentJob", "作文批改Agent（查询任务）"),
    ]),
    ("文本图像鉴伪", [
        ("RecognizeGeneralCardWarn", "通用卡证鉴伪"),
        ("VerifyGeneralCardWarn", "卡证鉴伪（大模型版）"),
        ("VerifyScenePhoto", "场景鉴伪（大模型版）"),
        ("VerifyBizLicenseEnterprise3", "营业执照核验（企业二或三要素）"),
        ("VerifyBizLicenseEnterprise4", "营业执照核验（企业四要素）"),
    ]),
    ("智能扫码", [
        ("QrcodeOCR", "二维码和条形码识别"),
    ]),
    ("汽车相关识别", [
        ("LicensePlateOCR", "车牌识别"),
        ("VinOCR", "车辆VIN码识别"),
    ]),
    ("仅老客户续费", [
        ("QuestionOCR", "试题识别"),
        ("RecognizeFormulaOCR", "公式识别"),
        ("PassportOCR", "护照识别（中国大陆地区护照）"),
        ("PermitOCR", "港澳台通行证识别"),
        ("GeneralEfficientOCR", "通用印刷体识别（精简版）"),
        ("GeneralFastOCR", "通用印刷体识别（高速版）"),
        ("TextDetect", "快速文本检测"),
        ("ArithmeticOCR", "算式识别"),
        ("SmartStructuralOCR", "智能结构化识别"),
        ("RideHailingDriverLicenseOCR", "网约车驾驶证识别"),
        ("RideHailingTransportLicenseOCR", "网约车运输证识别"),
        ("CarInvoiceOCR", "购车发票识别"),
        ("MixedInvoiceOCR", "混贴票据识别"),
        ("MixedInvoiceDetect", "混贴票据分类"),
        ("TableOCR", "表格识别（V1)"),
        ("TrainTicketOCR", "火车票识别"),
        ("WaybillOCR", "运单识别"),
        ("EstateCertOCR", "不动产权证识别"),
        ("ResidenceBookletOCR", "户口本识别"),
        ("EnterpriseLicenseOCR", "企业证照识别"),
        ("GeneralHandwritingOCR", "通用手写体识别"),
        ("EnglishOCR", "英文识别"),
        ("RecognizeTableOCR", "表格识别（V2)"),
        ("MLIDCardOCR", "马来西亚身份证识别"),
        ("RecognizeThaiIDCardOCR", "泰国身份证识别"),
        ("ImageEnhancement", "文本图像增强"),
    ]),
]

# 平铺索引：Action -> 中文名
ACTION_NAME_MAP: Dict[str, str] = {
    action: name for _, items in OCR_ACTION_CATALOG for action, name in items
}


def _build_payload(action: str, image_b64: str, multi_language: bool) -> Dict[str, Any]:
    """构造请求体：默认所有接口都接受 ImageBase64；个别接口附加专属参数。"""
    payload: Dict[str, Any] = {"ImageBase64": image_b64}
    if action == "GeneralAccurateOCR":
        payload["ConfigID"] = "MulOCR" if multi_language else "OCR"
    return payload


class TencentOcrClient:
    """
    直接调用腾讯云 v3 API（TC3-HMAC-SHA256 签名），避免引入较重的SDK依赖。
    """

    def __init__(self, cfg: TencentOcrConfig, session: Optional[requests.Session] = None):
        self.cfg = cfg
        self.session = session or requests.Session()

    def recognize(self, image_bytes: bytes) -> str:
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        payload = _build_payload(self.cfg.action, image_b64, self.cfg.multi_language)
        resp = self._call_api(action=self.cfg.action, payload=payload, version="2018-11-19")
        return self._extract_text(resp)

    # 提取结果时跳过这些纯技术字段（不参与文字内容输出）
    _SKIP_KEYS = {
        "RequestId", "Angle", "Angel", "Probability", "WordPolygon", "Polygon",
        "Coord", "CoordPoint", "LeftTop", "RightTop", "RightBottom", "LeftBottom",
        "WordCoordPoint", "ItemCoord", "CandWord", "WordInfo", "FaceRect",
        "WarnInfo", "HasWarn", "DetectInfo", "IsDup",
    }

    @classmethod
    def _extract_text(cls, resp: Dict[str, Any]) -> str:
        """通用文本提取：优先按已知结构读取；兜底递归收集所有字符串值。"""
        # 1) 通用 OCR 系列：TextDetections[].DetectedText
        if "TextDetections" in resp:
            lines = [
                (it.get("DetectedText") or "").strip()
                for it in (resp.get("TextDetections") or [])
            ]
            text = "\n".join(x for x in lines if x).strip()
            if text:
                return text
        # 2) 广告/门头识别：Items[].Name + Content
        if "Items" in resp:
            lines = []
            for it in (resp.get("Items") or []):
                name = (it.get("Name") or "").strip()
                content = (it.get("Content") or "").strip()
                if name and content:
                    lines.append(f"{name}: {content}")
                elif content:
                    lines.append(content)
            text = "\n".join(lines).strip()
            if text:
                return text
        # 3) 二维码/条码：CodeResults[].Data / TypeName
        if "CodeResults" in resp:
            lines = []
            for it in (resp.get("CodeResults") or []):
                data = (it.get("Data") or it.get("Url") or "").strip()
                tname = (it.get("TypeName") or "").strip()
                if data:
                    lines.append(f"{tname}: {data}" if tname else data)
            text = "\n".join(lines).strip()
            if text:
                return text
        # 4) 兜底：递归收集所有字符串字段值（卡证/票据等结构化接口）
        lines = cls._collect_strings(resp)
        text = "\n".join(lines).strip()
        return text or json.dumps(resp, ensure_ascii=False, indent=2)

    @classmethod
    def _collect_strings(cls, obj: Any, key: str = "") -> list:
        out = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in cls._SKIP_KEYS:
                    continue
                out.extend(cls._collect_strings(v, k))
        elif isinstance(obj, list):
            for it in obj:
                out.extend(cls._collect_strings(it, key))
        elif isinstance(obj, str):
            s = obj.strip()
            if s and key not in cls._SKIP_KEYS:
                out.append(s)
        return out

    def _call_api(self, action: str, payload: Dict[str, Any], version: str) -> Dict[str, Any]:
        endpoint = self.cfg.endpoint.rstrip("/")
        host = endpoint.replace("https://", "").replace("http://", "").strip("/")
        url = endpoint + "/"

        service = "ocr"
        http_request_method = "POST"
        canonical_uri = "/"
        canonical_querystring = ""
        canonical_headers = f"content-type:application/json; charset=utf-8\nhost:{host}\n"
        signed_headers = "content-type;host"
        payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        hashed_request_payload = _sha256_hex(payload_json)
        canonical_request = (
            f"{http_request_method}\n"
            f"{canonical_uri}\n"
            f"{canonical_querystring}\n"
            f"{canonical_headers}\n"
            f"{signed_headers}\n"
            f"{hashed_request_payload}"
        )

        timestamp = int(_dt.datetime.now(tz=_dt.timezone.utc).timestamp())
        date = _dt.datetime.fromtimestamp(timestamp, tz=_dt.timezone.utc).strftime("%Y-%m-%d")
        credential_scope = f"{date}/{service}/tc3_request"
        hashed_canonical_request = _sha256_hex(canonical_request.encode("utf-8"))
        string_to_sign = (
            "TC3-HMAC-SHA256\n"
            f"{timestamp}\n"
            f"{credential_scope}\n"
            f"{hashed_canonical_request}"
        )

        secret_date = _hmac_sha256(("TC3" + self.cfg.secret_key).encode("utf-8"), date)
        secret_service = _hmac_sha256(secret_date, service)
        secret_signing = _hmac_sha256(secret_service, "tc3_request")
        signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

        authorization = (
            "TC3-HMAC-SHA256 "
            f"Credential={self.cfg.secret_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, "
            f"Signature={signature}"
        )

        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Host": host,
            "X-TC-Action": action,
            "X-TC-Version": version,
            "X-TC-Region": self.cfg.region,
            "X-TC-Timestamp": str(timestamp),
            "Authorization": authorization,
        }

        r = self.session.post(url, data=payload_json, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        if "Response" not in data:
            raise RuntimeError(f"Unexpected response: {data}")
        resp = data["Response"]
        if "Error" in resp:
            e = resp["Error"]
            raise RuntimeError(f"{e.get('Code')}: {e.get('Message')}")
        return resp


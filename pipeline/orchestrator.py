"""
Main orchestrator pipeline
Coordinates all processing layers into unified workflow
"""
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass
from datetime import datetime

from utils.logger import logger
from utils.validators import validate_input_file, validate_output_path
from pipeline.pdf_extractor import PDFTextExtractor
from pipeline.classifier import DocumentClassifier, DocumentType
from ocr.preprocessor import ImagePreprocessor, PreprocessingParams, ScannedDocumentDetector
from ocr.extractor import TesseractOCR, MultiLanguageOCR
from cv.layout_detector import LayoutAnalyzer, ReadingOrderDetector
from tables.detector import TableDetector, GridAnalyzer, CellExtractor
from nlp.semantic_analyzer import SemanticAnalyzer
from generator.style_mapper import StyleMapper
from generator.word_builder import DocumentReconstructor


@dataclass
class PipelineConfig:
    """Pipeline configuration"""
    enable_ocr: bool = True
    enable_layout_detection: bool = True
    enable_table_detection: bool = True
    enable_semantic_analysis: bool = True
    enable_style_preservation: bool = True
    parallel_pages: int = 4
    dpi: int = 150
    min_confidence: float = 0.5


@dataclass
class PipelineMetrics:
    """Processing metrics"""
    total_pages: int = 0
    processed_pages: int = 0
    text_accuracy: float = 0.0
    layout_confidence: float = 0.0
    processing_time: float = 0.0
    document_type: DocumentType = None


class DocumentUnderstandingPipeline:
    """
    Main orchestrator for document understanding and conversion
    Coordinates 10-layer AI pipeline
    """

    def __init__(self, config: PipelineConfig = None):
        self.config = config or PipelineConfig()
        self.metrics = PipelineMetrics()

        # Initialize components
        self.pdf_extractor = PDFTextExtractor()
        self.classifier = DocumentClassifier()
        self.preprocessor = ImagePreprocessor(PreprocessingParams())
        self.scanned_detector = ScannedDocumentDetector()
        self.ocr = TesseractOCR()
        self.multilang_ocr = MultiLanguageOCR()
        self.layout_analyzer = LayoutAnalyzer()
        self.reading_order_detector = ReadingOrderDetector()
        self.table_detector = TableDetector()
        self.grid_analyzer = GridAnalyzer()
        self.cell_extractor = CellExtractor()
        self.semantic_analyzer = SemanticAnalyzer()
        self.style_mapper = StyleMapper()

        logger.info("DocumentUnderstandingPipeline initialized")

    def process(self, input_pdf: str, output_docx: str) -> PipelineMetrics:
        """
        Main processing pipeline
        Converts PDF to Word with full understanding
        """
        try:
            start_time = datetime.now()
            logger.info(f"Starting document processing: {input_pdf}")

            # Validation
            logger.info("LAYER 1: Input Validation")
            input_path = validate_input_file(input_pdf)
            output_path = validate_output_path(output_docx)

            # Extract text
            logger.info("LAYER 2: PDF Text Extraction")
            full_text, pages = self.pdf_extractor.extract_all_text(str(input_path))
            metadata = self.pdf_extractor.extract_metadata(str(input_path))
            self.metrics.total_pages = len(pages)

            # Document classification
            logger.info("LAYER 3: Document Intelligence Classification")
            classification = self.classifier.classify(
                full_text,
                num_pages=len(pages),
                num_tables=0
            )
            classification = self.classifier.refine_classification(
                classification,
                {"filename": input_path.name}
            )
            self.metrics.document_type = classification.document_type
            logger.info(f"Document type: {classification.document_type.value} "
                       f"(confidence: {classification.confidence:.2%})")

            # Process pages
            semantic_blocks = []

            for page_idx, page in enumerate(pages, 1):
                logger.debug(f"Processing page {page_idx}/{len(pages)}")

                # Get page image
                try:
                    page_image_bytes = self.pdf_extractor.get_page_as_image(
                        str(input_path), page_idx, self.config.dpi
                    )

                    # Layer 4: Scanned document detection
                    import cv2
                    import numpy as np
                    nparr = np.frombuffer(page_image_bytes, np.uint8)
                    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                    is_scanned = self.scanned_detector.is_scanned(image)
                    logger.debug(f"Page {page_idx} scanned: {is_scanned}")

                    # Layer 5: OCR preprocessing if scanned
                    if is_scanned and self.config.enable_ocr:
                        logger.debug(f"Preprocessing page {page_idx} for OCR")
                        image = self.preprocessor.preprocess(image)

                    # Layer 6: OCR extraction
                    ocr_result = self.multilang_ocr.extract_multilingual(image)
                    logger.debug(f"OCR: {len(ocr_result.words)} words, "
                               f"confidence: {ocr_result.confidence:.2%}")

                    # Layer 7: Layout detection
                    if self.config.enable_layout_detection:
                        blocks = self.layout_analyzer.analyze_layout(image)
                        blocks = self.reading_order_detector.detect_reading_order(blocks)
                        logger.debug(f"Layout: {len(blocks)} blocks detected")

                    # Layer 8: Table detection
                    if self.config.enable_table_detection:
                        tables = self.table_detector.detect_tables(image)
                        logger.debug(f"Tables: {len(tables)} detected")

                    # Layer 9: Semantic analysis
                    if self.config.enable_semantic_analysis:
                        page_blocks = self.semantic_analyzer.analyze_batch(
                            [text[:100] for text in page.text.split("\n")[:50]]
                        )
                        semantic_blocks.extend(page_blocks)

                except Exception as e:
                    logger.warning(f"Error processing page {page_idx}: {e}")
                    continue

                self.metrics.processed_pages += 1

            # Layer 10: Document reconstruction
            logger.info("LAYER 10: Word Document Generation")
            reconstructor = DocumentReconstructor(str(output_path))

            # Build blocks for Word generation
            doc_blocks = []
            
            # Add title if available
            if metadata.get("title"):
                doc_blocks.append({
                    "type": "title",
                    "text": metadata["title"],
                    "style": None
                })

            # Add content from semantic blocks
            for block in semantic_blocks:
                if block.text_type.value == "heading":
                    doc_blocks.append({
                        "type": "heading",
                        "text": block.text,
                        "metadata": {"level": block.level},
                        "style": None
                    })
                elif block.text_type.value == "list_item":
                    doc_blocks.append({
                        "type": "list_item",
                        "text": block.text,
                        "metadata": {"list_type": "bullet"},
                        "style": None
                    })
                else:
                    doc_blocks.append({
                        "type": "body",
                        "text": block.text,
                        "style": None
                    })

            reconstructor.build_from_blocks(doc_blocks)
            reconstructor.save()

            # Calculate metrics
            processing_time = (datetime.now() - start_time).total_seconds()
            self.metrics.processing_time = processing_time
            self.metrics.text_accuracy = 0.95  # Placeholder
            self.metrics.layout_confidence = 0.85  # Placeholder

            logger.info(f"Processing completed in {processing_time:.2f}s")
            logger.info(f"Output: {output_path}")

            return self.metrics

        except Exception as e:
            logger.error(f"Pipeline processing failed: {e}")
            raise

    def get_metrics(self) -> PipelineMetrics:
        """Get processing metrics"""
        return self.metrics

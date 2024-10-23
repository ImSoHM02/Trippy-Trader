import csv
import os
import sys
import requests
import xml.etree.ElementTree as ET

from collections import defaultdict
from io import BytesIO
from PyQt6.QtCore import Qt, QSortFilterProxyModel, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                           QComboBox, QLabel, QProgressDialog, QPushButton, QFileDialog,
                           QScrollArea, QFrame, QMessageBox, QCheckBox, QLineEdit)




class ImageLoader(QThread):
    image_loaded = pyqtSignal(str, QPixmap)
    
    def __init__(self, url, filename):
        super().__init__()
        self.url = url
        self.filename = filename
        self._is_running = True
        
    def stop(self):
        self._is_running = False
        self.wait()  # Wait for the thread to finish
        
    def run(self):
        if not self._is_running:
            return
            
        try:
            response = requests.get(self.url)
            if not self._is_running:  # Check if we should continue
                return
                
            image_data = BytesIO(response.content)
            pixmap = QPixmap()
            pixmap.loadFromData(image_data.getvalue())
            
            if not self._is_running:  # Check if we should continue
                return
                
            # Scale to 30%
            scaled_pixmap = pixmap.scaled(
                int(pixmap.width() * 0.3), 
                int(pixmap.height() * 0.3),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            
            if self._is_running:  # Only emit if we're still running
                self.image_loaded.emit(self.filename, scaled_pixmap)
        except Exception as e:
            print(f"Error loading image {self.url}: {str(e)}")

class ImageWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        self.layout = QVBoxLayout(self)
        self.image_label = QLabel()
        self.info_label = QLabel()
        self.info_label.setWordWrap(True)
        
        # Add checkbox for selection
        self.checkbox = QCheckBox("Select for Export")
        
        self.layout.addWidget(self.image_label)
        self.layout.addWidget(self.info_label)
        self.layout.addWidget(self.checkbox)
        
        # Store the image URL
        self.image_url = ""
        
        # Set minimum size for the widget
        self.setMinimumWidth(200)
        self.setMinimumHeight(200)

class SearchableComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setMaxVisibleItems(20)
        
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.model())
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        
        self.all_items = []
        
    def addItems(self, items):
        self.all_items = items
        super().addItems(items)
        
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            search_text = self.currentText().lower()
            filtered_items = [item for item in self.all_items 
                            if search_text in item.lower()]
            self.clear()
            super().addItems(filtered_items)
            if filtered_items:
                self.showPopup()
            self.setEditText(search_text)
        elif event.key() == Qt.Key.Key_Escape:
            self.clear()
            super().addItems(self.all_items)
            self.hidePopup()
        else:
            super().keyPressEvent(event)

    def focusOutEvent(self, event):
        if not self.view().isVisible():
            super().focusOutEvent(event)

class GameBrowser(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Trippy Trader")
        self.setMinimumSize(1200, 800)
        
        self.platforms = set()
        self.regions = set()
        self.games_by_platform = defaultdict(list)
        self.games_data = {}
        self.images_data = defaultdict(list)
        self.image_loaders = []
        
        # Create main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        
        # Create button layout
        button_layout = QHBoxLayout()
        
        # Add file selection button
        self.file_button = QPushButton("Select XML File")
        self.file_button.clicked.connect(self.select_file)
        button_layout.addWidget(self.file_button)
        
        # Add export button
        self.export_button = QPushButton("Export Selected to CSV")
        self.export_button.clicked.connect(self.export_to_csv)
        button_layout.addWidget(self.export_button)
        
        # Add button layout to main layout
        main_layout.addLayout(button_layout)
        
        self.platform_combo = SearchableComboBox()
        self.game_combo = SearchableComboBox()
        self.region_combo = SearchableComboBox()
        
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        self.image_container = QWidget()
        self.image_layout = QHBoxLayout(self.image_container)
        self.image_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.scroll_area.setWidget(self.image_container)
        
        self.create_ui(main_layout)
        
        self.debug_label = QLabel()
        main_layout.addWidget(self.debug_label)
        
        self.platform_combo.currentTextChanged.connect(self.on_platform_changed)
        self.game_combo.currentTextChanged.connect(self.on_game_changed)
        self.region_combo.currentTextChanged.connect(self.update_image_display)

    def closeEvent(self, event):
        """Handle application closing"""
        self.stop_image_loaders()
        super().closeEvent(event)

    def stop_image_loaders(self):
        """Stop all running image loaders"""
        for loader in self.image_loaders:
            if loader.isRunning():
                loader.stop()
                loader.wait()  # Wait for the thread to finish
        self.image_loaders.clear()

    def select_file(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Select XML File", "", "XML Files (*.xml)")
        if file_name:
            self.load_xml_data(file_name)

    def create_ui(self, layout):
        layout.addWidget(QLabel("Select Platform:"))
        layout.addWidget(self.platform_combo)
        
        layout.addWidget(QLabel("Select Game:"))
        layout.addWidget(self.game_combo)
        
        layout.addWidget(QLabel("Select Region:"))
        layout.addWidget(self.region_combo)
        
        # Add custom tags input
        layout.addWidget(QLabel("Additional Tags (comma separated):"))
        self.custom_tags_input = QLineEdit()
        self.custom_tags_input.setPlaceholderText("Enter additional tags, separated by commas")
        layout.addWidget(self.custom_tags_input)
        
        self.details_labels = {
            'Name': QLabel(),
            'ReleaseDate': QLabel(),
            'Developer': QLabel(),
            'Publisher': QLabel(),
            'Genres': QLabel(),
            'Overview': QLabel(),
        }
        
        for label in self.details_labels.values():
            label.setWordWrap(True)
            layout.addWidget(label)
        
        layout.addWidget(self.scroll_area)
        layout.addStretch()

    def parse_element(self, buffer, tag_type):
        try:
            element = ET.fromstring(buffer)
            data = {}
            database_id = None
            
            for child in element:
                if child.text:
                    data[child.tag] = child.text.strip()
                    if child.tag == 'DatabaseID':
                        database_id = child.text.strip()
                    elif child.tag == 'Region':
                        self.regions.add(child.text.strip())
            
            return database_id, data
        except ET.ParseError as e:
            print(f"Error parsing {tag_type}: {e}")
            print(f"Problematic XML: {buffer[:200]}...")
            return None, None

    def load_xml_data(self, xml_file_path):
        try:
            progress = QProgressDialog("Loading XML data...", None, 0, 100, self)
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.show()
            
            print(f"Starting XML parsing of file: {xml_file_path}")
            
            # Clear existing data
            self.stop_image_loaders()
            self.clear_images()
            self.platforms.clear()
            self.regions.clear()
            self.games_by_platform.clear()
            self.games_data.clear()
            self.images_data.clear()
            
            with open(xml_file_path, 'r', encoding='utf-8') as file:
                buffer = ""
                in_tag = False
                current_tag = None
                processed_elements = 0
                
                for line in file:
                    if '<Game>' in line:
                        in_tag = True
                        current_tag = 'Game'
                        buffer = line
                    elif '<GameImage>' in line:
                        in_tag = True
                        current_tag = 'GameImage'
                        buffer = line
                    elif '</Game>' in line and current_tag == 'Game':
                        buffer += line
                        database_id, game_data = self.parse_element(buffer, 'Game')
                        
                        if database_id and game_data:
                            if 'Platform' in game_data:
                                platform = game_data['Platform']
                                self.platforms.add(platform)
                                self.games_data[database_id] = game_data
                                self.games_by_platform[platform].append(game_data)
                                
                                processed_elements += 1
                                if processed_elements % 100 == 0:
                                    progress.setValue(processed_elements % 100)
                        
                        buffer = ""
                        in_tag = False
                        current_tag = None
                        
                    elif '</GameImage>' in line and current_tag == 'GameImage':
                        buffer += line
                        database_id, image_data = self.parse_element(buffer, 'GameImage')
                        
                        if database_id and image_data:
                            self.images_data[database_id].append(image_data)
                        
                        buffer = ""
                        in_tag = False
                        current_tag = None
                        
                    elif in_tag:
                        buffer += line

            # Update UI
            self.platform_combo.clear()
            self.platform_combo.addItems(sorted(self.platforms))
            self.platform_combo.setCurrentText("")
            self.platform_combo.lineEdit().setPlaceholderText("Search platforms...")
            
            self.debug_label.setText(
                f"Loaded {len(self.platforms)} platforms, {len(self.games_data)} games, "
                f"and {sum(len(imgs) for imgs in self.images_data.values())} total images"
            )
            
        except Exception as e:
            print(f"Error loading XML: {str(e)}")
            self.debug_label.setText(f"Error loading XML: {str(e)}")
            import traceback
            traceback.print_exc()
        
        finally:
            progress.close()

    def clear_images(self):
        """Clear images and stop loaders"""
        self.stop_image_loaders()
        while self.image_layout.count():
            item = self.image_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def on_platform_changed(self, platform):
        """Handle platform selection change"""
        self.stop_image_loaders()
        self.clear_images()
        self.game_combo.clear()
        self.region_combo.clear()
        if platform:
            print(f"Loading games for platform: {platform}")
            games = sorted(self.games_by_platform[platform], key=lambda x: x.get('Name', ''))
            self.game_combo.addItems([game['Name'] for game in games])
            self.game_combo.setCurrentText("")
            self.game_combo.lineEdit().setPlaceholderText("Search games...")

    def get_game_regions(self, database_id):
        """Get all unique regions for a specific game's images"""
        if database_id in self.images_data:
            regions = set()
            for image in self.images_data[database_id]:
                if 'Region' in image:
                    regions.add(image['Region'])
            return sorted(regions)
        return []

    def on_image_loaded(self, filename, pixmap):
        """Handle loaded image"""
        image_widget = ImageWidget()
        image_widget.image_label.setPixmap(pixmap)
        image_widget.info_label.setText(filename)
        self.image_layout.addWidget(image_widget)

    def update_image_display(self):
        """Update the image display for the selected game and region"""
        self.stop_image_loaders()
        self.clear_images()
        
        game_name = self.game_combo.currentText()
        if not game_name:
            return
            
        platform = self.platform_combo.currentText()
        selected_region = self.region_combo.currentText()
        
        game_data = next((game for game in self.games_by_platform[platform] 
                         if game['Name'] == game_name), None)
        
        if game_data and selected_region:
            database_id = game_data.get('DatabaseID')
            if database_id:
                all_images = self.images_data.get(database_id, [])
                images = [img for img in all_images if img.get('Region') == selected_region]
                
                for img in images:
                    filename = img.get('FileName')
                    if filename:
                        url = f"https://images.launchbox-app.com/{filename}"
                        loader = ImageLoader(url, filename)
                        loader.image_loaded.connect(self.on_image_loaded)
                        self.image_loaders.append(loader)
                        loader.start()

    def on_game_changed(self, game_name):
        """Handle game selection change"""
        self.stop_image_loaders()
        self.clear_images()

        if not game_name:
            return

        platform = self.platform_combo.currentText()
        game_data = next((game for game in self.games_by_platform[platform] 
                         if game['Name'] == game_name), None)

        if game_data:
            self.details_labels['Name'].setText(f"Name: {game_data.get('Name', 'N/A')}")
            self.details_labels['ReleaseDate'].setText(
                f"Release Date: {game_data.get('ReleaseDate', 'N/A')}")
            self.details_labels['Developer'].setText(
                f"Developer: {game_data.get('Developer', 'N/A')}")
            self.details_labels['Publisher'].setText(
                f"Publisher: {game_data.get('Publisher', 'N/A')}")
            self.details_labels['Genres'].setText(f"Genres: {game_data.get('Genres', 'N/A')}")

            overview = game_data.get('Overview', 'N/A')
            if len(overview) > 500:
                overview = overview[:497] + "..."
            self.details_labels['Overview'].setText(f"Overview: {overview}")

            database_id = game_data.get('DatabaseID')
            if database_id:
                self.region_combo.clear()
                available_regions = self.get_game_regions(database_id)
                if available_regions:
                    self.region_combo.addItems(available_regions)
                    self.region_combo.setCurrentIndex(0)
                    self.region_combo.lineEdit().setPlaceholderText("Search regions...")
                    self.update_image_display()
                else:
                    self.clear_images()
        
    def export_to_csv(self):
        """Export selected game data to CSV"""
        if not self.game_combo.currentText():
            QMessageBox.warning(self, "Warning", "Please select a game first")
            return

        # Get current game data
        platform = self.platform_combo.currentText()
        game_name = self.game_combo.currentText()
        game_data = next((game for game in self.games_by_platform[platform] 
                         if game['Name'] == game_name), None)

        if not game_data:
            return

        # Get selected image URL
        selected_image_url = None
        for i in range(self.image_layout.count()):
            widget = self.image_layout.itemAt(i).widget()
            if isinstance(widget, ImageWidget) and widget.checkbox.isChecked():
                selected_image_url = widget.image_url
                break
            
        if not selected_image_url:
            QMessageBox.warning(self, "Warning", "Please select an image")
            return

        # Get region and determine region code
        region = self.region_combo.currentText()
        region_code = self.get_region_code(region)

        # Create handle (slug)
        handle = f"{game_data['Name']}-{platform}-{region_code}".lower()
        handle = handle.replace(' ', '-').replace('&', 'and')
        handle = ''.join(c for c in handle if c.isalnum() or c == '-')

        # Create title with region code
        title = f"{game_data['Name']} {platform} Game {region_code}"

        # Create product category
        product_category = f"Gaming > {platform}"

        # Create tags with custom tags
        base_tags = [game_data['Name'], platform]
        if platform.lower() == "playstation 2":
            base_tags.extend(["PS2", "PlayStation2"])
        # Add more platform aliases as needed

        # Add custom tags
        custom_tags = [tag.strip() for tag in self.custom_tags_input.text().split(',') if tag.strip()]
        all_tags = base_tags + custom_tags
        tags = ', '.join(all_tags)

        # Create CSV row with proper quote handling
        row = {
            'Handle': handle,
            'Title': title,
            'Body (HTML)': game_data.get('Overview', ''),
            'Vendor': 'Trippy Trades',
            'Product Category': product_category,
            'Type': 'Video Games & Consoles: Video Games',
            'Tags': tags,
            'Published': 'true',
            'Option1 Name': 'Title',
            'Option1 Value': 'Default Title',
            'Variant Grams': '150.0',
            'Variant Inventory Tracker': 'shopify',
            'Variant Inventory Policy': 'deny',
            'Variant Fulfillment Service': 'manual',
            'Variant Requires Shipping': 'true',
            'Variant Taxable': 'true',
            'Image Src': selected_image_url,
            'SEO Title': title,
            'SEO Description': game_data.get('Overview', ''),
            'Variant Weight Unit': 'kg',
            'Status': 'active'
        }

        # Write to CSV with proper quote handling
        try:
            file_exists = os.path.isfile('game_export.csv')
            with open('game_export.csv', 'a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
                if not file_exists:
                    writer.writeheader()

                # Handle quotes properly
                processed_row = {}
                for key, value in row.items():
                    if isinstance(value, str):
                        if ',' in value and not (value.startswith('"') and value.endswith('"')):
                            processed_row[key] = f'"{value}"'
                        else:
                            processed_row[key] = value
                    else:
                        processed_row[key] = value

                writer.writerow(processed_row)

            QMessageBox.information(self, "Success", "Game data exported successfully!")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export: {str(e)}")
            
    def get_region_code(self, region):
        """Get standardized region code"""
        if region in ["USA", "North America", "Canada"]:
            return "NTSC-U/C"
        elif region in ["Japan", "South Korea", "Taiwan", "Hong Kong"]:
            return "NTSC-J"
        elif region in ["China"]:
            return "NTSC-C"
        elif region in ["Europe", "Australia", "New Zealand", "Germany", "United Kingdom"]:
            return "PAL"
        return region  # Return original region if no match
        
    def on_image_loaded(self, filename, pixmap):
        """Handle loaded image with URL storage"""
        image_widget = ImageWidget()
        image_widget.image_label.setPixmap(pixmap)
        image_widget.info_label.setText(filename)
        image_widget.image_url = f"https://images.launchbox-app.com/{filename}"
        self.image_layout.addWidget(image_widget)

CSV_FIELDS = [
    'Handle', 'Title', 'Body (HTML)', 'Vendor', 'Product Category', 'Type', 'Tags',
    'Published', 'Option1 Name', 'Option1 Value', 'Option1 Linked To', 'Option2 Name',
    'Option2 Value', 'Option2 Linked To', 'Option3 Name', 'Option3 Value',
    'Option3 Linked To', 'Variant SKU', 'Variant Grams', 'Variant Inventory Tracker',
    'Variant Inventory Policy', 'Variant Fulfillment Service', 'Variant Price',
    'Variant Compare At Price', 'Variant Requires Shipping', 'Variant Taxable',
    'Variant Barcode', 'Image Src', 'Image Position', 'Image Alt Text', 'Gift Card',
    'SEO Title', 'SEO Description', 'Google Shopping / Google Product Category',
    'Google Shopping / Gender', 'Google Shopping / Age Group', 'Google Shopping / MPN',
    'Google Shopping / Condition', 'Google Shopping / Custom Product',
    'Google Shopping / Custom Label 0', 'Google Shopping / Custom Label 1',
    'Google Shopping / Custom Label 2', 'Google Shopping / Custom Label 3',
    'Google Shopping / Custom Label 4',
    'EComposer product countdown end at (product.metafields.ecomposer.countdown)',
    'EComposer product countdown start at (product.metafields.ecomposer.countdown_from)',
    'Google: Custom Product (product.metafields.mm-google-shopping.custom_product)',
    'Recommended age group (product.metafields.shopify.recommended-age-group)',
    'Toy figure features (product.metafields.shopify.toy-figure-features)',
    'Video game genre (product.metafields.shopify.video-game-genre)',
    'Video game platform (product.metafields.shopify.video-game-platform)',
    'Video game sub-genre (product.metafields.shopify.video-game-sub-genre)',
    'Complementary products (product.metafields.shopify--discovery--product_recommendation.complementary_products)',
    'Related products (product.metafields.shopify--discovery--product_recommendation.related_products)',
    'Related products settings (product.metafields.shopify--discovery--product_recommendation.related_products_display)',
    'Variant Image', 'Variant Weight Unit', 'Variant Tax Code', 'Cost per item',
    'Included / Australia', 'Price / Australia', 'Compare At Price / Australia',
    'Included / new zealand', 'Price / new zealand', 'Compare At Price / new zealand',
    'Included / world wide', 'Price / world wide', 'Compare At Price / world wide',
    'Status'
]

def main():
    app = QApplication(sys.argv)
    window = GameBrowser()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
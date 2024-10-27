import csv
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from time import sleep
import requests
from PyQt6.QtCore import Qt, QSortFilterProxyModel, QThread, pyqtSignal, QSettings, QTimer
from PyQt6.QtGui import QIcon, QPixmap, QIntValidator
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QComboBox, QLabel, QProgressDialog, QPushButton, QScrollArea, 
    QFrame, QMessageBox, QCheckBox, QLineEdit, QGridLayout,
    QSizePolicy, QDialog, QDialogButtonBox
)
from io import BytesIO

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

# Configuration dataclass for MobyGames API
@dataclass
class MobyGamesConfig:
    api_key: str
    base_url: str = "https://api.mobygames.com/v1"
    rate_limit: float = 1.0  # Time between requests in seconds
    cache_dir: str = "cache"

class APIKeyDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("MobyGames API Key")
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        
        # Add explanation label
        layout.addWidget(QLabel(
            "Please enter your MobyGames API key.\n"
            "You can get one from: https://www.mobygames.com/info/api/"
        ))
        
        # Add input field
        self.key_input = QLineEdit()
        layout.addWidget(self.key_input)
        
        # Add buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        # Load existing key if any
        settings = QSettings('TrippyTrader', 'MobyGames')
        saved_key = settings.value('api_key', '')
        if saved_key:
            self.key_input.setText(saved_key)
    
    def get_api_key(self):
        return self.key_input.text().strip()

class ImageLoader(QThread):
    image_loaded = pyqtSignal(str, QPixmap)
    
    def __init__(self, url, identifier):
        super().__init__()
        self.url = url
        self.identifier = identifier
        self._is_running = True
        
    def stop(self):
        self._is_running = False
        self.wait()
        
    def run(self):
        if not self._is_running:
            return
            
        try:
            response = requests.get(self.url)
            if not self._is_running:
                return
                
            image_data = BytesIO(response.content)
            pixmap = QPixmap()
            pixmap.loadFromData(image_data.getvalue())
            
            if not self._is_running:
                return
                
            # Scale to 30%
            scaled_pixmap = pixmap.scaled(
                int(pixmap.width() * 0.3), 
                int(pixmap.height() * 0.3),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            
            if self._is_running:
                self.image_loaded.emit(self.identifier, scaled_pixmap)
        except Exception as e:
            print(f"Error loading image {self.url}: {str(e)}")

class ImageWidget(QFrame):
    def __init__(self, image_url=None, image_type=None, region=None, parent=None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(5)
        self.layout.setContentsMargins(5, 5, 5, 5)
        
        # Image display
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setFixedSize(200, 200)
        
        # Info layout
        info_layout = QVBoxLayout()
        
        # Image type label
        if image_type:
            self.type_label = QLabel(f"<b>{image_type}</b>")
            self.type_label.setStyleSheet("color: #2c3e50;")
            self.type_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            info_layout.addWidget(self.type_label)
        
        # Region label
        if region:
            self.region_label = QLabel(f"Region: {region}")
            self.region_label.setStyleSheet("color: #7f8c8d;")
            self.region_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            info_layout.addWidget(self.region_label)
        
        # Checkbox for selection
        self.checkbox = QCheckBox("Select for Export")
        self.checkbox.setStyleSheet("""
            QCheckBox {
                padding: 5px;
                border-radius: 3px;
            }
            QCheckBox:hover {
                background-color: #f0f0f0;
            }
        """)
        
        # Add widgets to layout
        self.layout.addWidget(self.image_label)
        self.layout.addLayout(info_layout)
        self.layout.addWidget(self.checkbox)
        
        # Store image URL
        self.image_url = image_url
        
        # Set focus policy
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        # Add hover effect
        self.setStyleSheet("""
            QFrame {
                border: 1px solid #ddd;
                border-radius: 5px;
                padding: 5px;
                background-color: white;
            }
            QFrame:hover {
                border: 1px solid #3498db;
                background-color: #f8f9fa;
            }
        """)

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
            
class MobyGamesAPI:
    def __init__(self, config: MobyGamesConfig):
        self.config = config
        self.last_request_time = 0  # Initialize to 0
        
        # Create cache directory if it doesn't exist
        os.makedirs(self.config.cache_dir, exist_ok=True)
    
    def _rate_limit(self):
        #Implement rate limiting
        current_time = datetime.now()
        time_since_last = (current_time - datetime.fromtimestamp(self.last_request_time)).total_seconds() if self.last_request_time > 0 else float('inf')
        
        if time_since_last < self.config.rate_limit:
            sleep(self.config.rate_limit - time_since_last)
        
        self.last_request_time = current_time.timestamp()
    
    def _get_cache_path(self, endpoint: str, params: Dict = None) -> str:
        #Generate cache file path for request
        params_str = '_'.join(f"{k}-{v}" for k, v in (params or {}).items())
        filename = f"{endpoint.replace('/', '_')}_{params_str}.json".replace('?', '_')
        return os.path.join(self.config.cache_dir, filename)
    
    def _make_request(self, endpoint: str, params: Dict = None) -> Dict:
        #Make an API request with rate limiting and caching
        cache_path = self._get_cache_path(endpoint, params)
        
        # Check cache first
        if os.path.exists(cache_path):
            with open(cache_path, 'r') as f:
                return eval(f.read())  # Using eval since json.loads doesn't handle single quotes
        
        # Make actual request
        self._rate_limit()
        url = f"{self.config.base_url}/{endpoint}"
        params = params or {}
        params['api_key'] = self.config.api_key
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        # Cache the response
        with open(cache_path, 'w') as f:
            f.write(str(data))
        
        return data
    
    def get_platforms(self) -> List[Dict]:
        #Get all available platforms
        response = self._make_request('platforms')
        return response.get('platforms', [])
    
    def get_games_by_platform(self, platform_id: int) -> List[Dict]:
        #Get all games for a specific platform, handling pagination
        all_games = []
        offset = 0
        total = None

        while total is None or offset < total:
            response = self._make_request('games', {
                'platform': platform_id,
                'offset': offset,
                'limit': 100,
                'format': 'brief'  # Request minimal data
            })

            games = response.get('games', [])
            all_games.extend(games)

            # Get total count from first response
            if total is None:
                total = response.get('total_count', 0)

            # Update offset for next page
            offset += len(games)

            # Break if we got fewer games than requested (last page)
            if len(games) < 100:
                break
            
        return all_games
    
    def get_game(self, game_id: int) -> Dict:
        #Get detailed information about a specific game
        return self._make_request(f'games/{game_id}')
    
    def get_game_platform_covers(self, game_id: int, platform_id: int) -> Dict:
        #Get covers for a specific game and platform
        return self._make_request(f'games/{game_id}/platforms/{platform_id}/covers')
            
    def search_games_by_platform(self, platform_id: int, search_term: str) -> List[Dict]:
        #Search for games on a specific platform
        response = self._make_request('games', {
            'platform': platform_id,
            'title': search_term,
            'format': 'brief',
            'limit': 100  # Keep reasonable limit for search results
        })
        return response.get('games', [])

class GameBrowser(QMainWindow):
    def __init__(self):
        super().__init__()
        self.variants = [
            "Black Label - Very Good",
            "Black Label - Good",
            "Black Label - Damaged",
            "Black Label - Very Good + Manual",
            "Black Label - Good + Manual",
            "Black Label - Damaged + Manual",
            "Platinum - Very Good",
            "Platinum - Good",
            "Platinum - Damaged",
            "Platinum - Very Good + Manual",
            "Platinum - Good + Manual",
            "Platinum - Damaged + Manual",
            "Disk Only"
        ]
        
        self.setWindowTitle("Trippy Trader - Sugondese Edition v0.69")
        self.setMinimumSize(1200, 800)
        
        # Initialize the status bar
        self.statusBar()  # This creates the status bar

        # Create a message label for the status bar
        self.message_label = QLabel()
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message_label.setStyleSheet("color: green;")
        self.statusBar().addPermanentWidget(self.message_label, 1)
        
        # Set window icon and initialize data structures
        icon_path = Path("assets/icon.png")  # Adjust path as needed
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        
        # Initialize settings and API
        settings = QSettings('TrippyTrader', 'MobyGames')
        api_key = settings.value('api_key', '')

        # Initialize details_labels for displaying game information
        self.details_labels = {'Name': QLabel()}  # Ensure it is available throughout the class

        if not api_key:
            dialog = APIKeyDialog(self)
            if dialog.exec():
                api_key = dialog.get_api_key()
                settings.setValue('api_key', api_key)
            else:
                sys.exit(0)
        
        # Initialize MobyGames API
        config = MobyGamesConfig(
            api_key=api_key,
            cache_dir="mobygames_cache"
        )
        self.api = MobyGamesAPI(config)
        
        # Initialize data structures
        self.platforms = {}  # id: name mapping
        self.current_games = []  # Current list of games for selected platform
        self.current_game_details = None
        self.image_loaders = []
        
        # Create main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        
        # Add header image (centered at the top)
        header_layout = QHBoxLayout()
        header_image_path = Path("assets/header.png")  # Adjust path as needed
        if header_image_path.exists():
            header_label = QLabel()
            header_pixmap = QPixmap(str(header_image_path))
            # Scale the header image to fit the width while maintaining aspect ratio
            scaled_header = header_pixmap.scaledToWidth(
                210,  # Slightly less than window width to account for margins
                Qt.TransformationMode.SmoothTransformation
            )
            header_label.setPixmap(scaled_header)
            header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            header_layout.addWidget(header_label)
            main_layout.addLayout(header_layout)
        
        # Call create_ui to build the UI
        self.create_ui(main_layout)
        
        # Load initial data
        self.load_platforms()
    
    def create_ui(self, layout):
        # Create container for upper content
        upper_container = QWidget()
        upper_layout = QVBoxLayout(upper_container)
        upper_layout.setContentsMargins(0, 0, 0, 0)

        # Platform selection
        upper_layout.addWidget(QLabel("Select Platform:"))
        self.platform_combo = SearchableComboBox()
        upper_layout.addWidget(self.platform_combo)

        # Game search
        upper_layout.addWidget(QLabel("Search Game:"))
        self.game_search = QLineEdit()
        self.game_search.setPlaceholderText("Type game name and press Enter...")
        self.game_search.returnPressed.connect(self.search_games)
        upper_layout.addWidget(self.game_search)

        # Game results combo
        self.game_results_combo = QComboBox()
        self.game_results_combo.setVisible(False)
        self.game_results_combo.currentTextChanged.connect(self.on_game_selected)
        upper_layout.addWidget(self.game_results_combo)

        # Region selection
        upper_layout.addWidget(QLabel("Select Region:"))
        self.region_code_combo = QComboBox()
        self.region_code_combo.currentTextChanged.connect(self.on_region_changed)
        upper_layout.addWidget(self.region_code_combo)

        # Scan type selection
        upper_layout.addWidget(QLabel("Select Cover Type:"))
        self.scan_type_combo = QComboBox()
        self.scan_type_combo.currentTextChanged.connect(self.on_scan_type_changed)
        upper_layout.addWidget(self.scan_type_combo)
        
        # Custom region selection
        upper_layout.addWidget(QLabel("Custom Region (overrides region in export):"))
        self.custom_region_input = QLineEdit()
        self.custom_region_input.setPlaceholderText("Leave empty to use selected region")
        upper_layout.addWidget(self.custom_region_input)
        
        # Custom image URL
        upper_layout.addWidget(QLabel("Custom Image URL (used if no image selected):"))
        self.custom_image_url = QLineEdit()
        self.custom_image_url.setPlaceholderText("Enter URL for custom image or leave empty")
        upper_layout.addWidget(self.custom_image_url)
        
        # Variant selection
        upper_layout.addWidget(QLabel("Select Variant:"))
        self.variant_combo = QComboBox()
        self.variant_combo.addItems(self.variants)
        self.variant_combo.setCurrentIndex(0)  # Default to first variant
        upper_layout.addWidget(self.variant_combo)
        
        inventory_group = QWidget()
        inventory_layout = QHBoxLayout(inventory_group)

        # Location input
        location_label = QLabel("Location:")
        self.location_input = QLineEdit()
        self.location_input.setText("In-Store Reservoir")
        self.location_input.setPlaceholderText("Enter location name")
        inventory_layout.addWidget(location_label)
        inventory_layout.addWidget(self.location_input)

        # Quantity input
        quantity_label = QLabel("Quantity:")
        self.quantity_input = QLineEdit()
        self.quantity_input.setText("0")
        self.quantity_input.setPlaceholderText("Enter quantity")
        self.quantity_input.setValidator(QIntValidator(0, 9999))
        inventory_layout.addWidget(quantity_label)
        inventory_layout.addWidget(self.quantity_input)

        upper_layout.addWidget(inventory_group)


        # Additional tags
        upper_layout.addWidget(QLabel("Additional Tags (comma separated):"))
        self.custom_tags_input = QLineEdit()
        upper_layout.addWidget(self.custom_tags_input)

        # Name label
        self.details_labels = {
            'Name': QLabel()
        }
        self.details_labels['Name'].setWordWrap(True)
        upper_layout.addWidget(self.details_labels['Name'])

        # Add upper container to main layout
        layout.addWidget(upper_container)

        # Set up scroll area and image container
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        self.image_container = QWidget()
        self.image_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        self.image_layout = QGridLayout(self.image_container)
        self.image_layout.setSpacing(10)
        self.image_layout.setContentsMargins(10, 10, 10, 10)
        self.image_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        
        self.scroll_area.setWidget(self.image_container)
        layout.addWidget(self.scroll_area, 1)

        # Bottom button layout (side-by-side buttons)
        bottom_button_layout = QHBoxLayout()

        # Add export button
        self.export_button = QPushButton("Export Selected to CSV")
        self.export_button.setFixedWidth(200)  # Fixed width for consistent sizing
        self.export_button.clicked.connect(self.export_to_csv)
        bottom_button_layout.addWidget(self.export_button)

        # Add refresh cache button
        self.refresh_button = QPushButton("Refresh Cache")
        self.refresh_button.setFixedWidth(200)  # Fixed width for consistent sizing
        self.refresh_button.clicked.connect(self.refresh_cache)
        bottom_button_layout.addWidget(self.refresh_button)

        # Align buttons at the bottom of the window
        layout.addLayout(bottom_button_layout)

        # Add debug label (optional, can be removed later)
        self.debug_label = QLabel()
        layout.addWidget(self.debug_label)
    
    def populate_scan_types(self, covers: Dict):
        #Populate scan type dropdown with available types
        unique_scan_types = set()

        # Collect all unique scan types from cover groups
        for group in self.cover_groups:
            for cover in group.get('covers', []):
                scan_type = cover.get('scan_of', 'Unknown')
                if scan_type:
                    unique_scan_types.add(scan_type)

        # Update scan type combo box
        self.scan_type_combo.clear()
        self.scan_type_combo.addItem("Select cover type...")  # Add default option
        if unique_scan_types:
            # Sort and add scan types
            for scan_type in sorted(unique_scan_types):
                self.scan_type_combo.addItem(scan_type)

        print(f"Available scan types: {sorted(unique_scan_types)}")

        # Clear any existing images
        self.clear_images()

    def closeEvent(self, event):
        #Handle application closing
        self.stop_image_loaders()
        super().closeEvent(event)

    def stop_image_loaders(self):
        #Stop all running image loaders
        for loader in self.image_loaders:
            if loader.isRunning():
                loader.stop()
                loader.wait()
        self.image_loaders.clear()

    def load_platforms(self):
        #Load platforms from MobyGames API
        try:
            progress = QProgressDialog("Loading platforms...", "Cancel", 0, 100, self)
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.setAutoClose(True)
            progress.setValue(0)

            platforms = self.api.get_platforms()
            print(f"Loaded {len(platforms)} platforms")

            # Store both id and name for each platform
            self.platforms = {p['platform_name']: p['platform_id'] for p in platforms}

            self.platform_combo.clear()
            self.platform_combo.addItems(sorted(self.platforms.keys()))
            self.platform_combo.setCurrentText("")
            self.platform_combo.lineEdit().setPlaceholderText("Search platforms...")

            progress.setValue(100)

        except Exception as e:
            print(f"Error loading platforms: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to load platforms: {str(e)}")

    def populate_regions(self, covers: Dict):
        #Populate region dropdown with unique regions from cover groups
        unique_regions = set()
        self.cover_groups = covers.get('cover_groups', [])

        print("\nProcessing cover groups response:")
        print(f"Number of cover groups: {len(self.cover_groups)}")

        # Collect all unique regions from cover groups
        for group in self.cover_groups:
            countries = group.get('countries', [])
            print(f"Cover group countries: {countries}")
            for country in countries:
                unique_regions.add(country)

        print(f"Total unique regions found: {len(unique_regions)}")
        print(f"Regions: {sorted(unique_regions)}\n")

        # Update region combo box
        self.region_code_combo.clear()
        if unique_regions:
            sorted_regions = sorted(unique_regions)
            self.region_code_combo.addItems(sorted_regions)

            # Try to select a preferred region if available
            preferred_regions = ['United States', 'Australia', 'Europe', 'Japan']
            for region in preferred_regions:
                if region in sorted_regions:
                    index = sorted_regions.index(region)
                    self.region_code_combo.setCurrentIndex(index)
                    break
            else:
                # If no preferred region found, select the first one
                self.region_code_combo.setCurrentIndex(0)
        else:
            self.region_code_combo.addItem("No regions available")
            print("Warning: No regions found in cover groups")

        # Clear any existing images
        self.clear_images()

    def on_region_changed(self, region: str):
        #Handle region selection change
        print(f"\nRegion changed to: {region}")
        # Only display covers if we have both region and scan type selected
        if hasattr(self, 'cover_groups') and self.scan_type_combo.currentText() != "Select cover type...":
            self.display_covers_for_region(region, self.scan_type_combo.currentText())
        else:
            print("Waiting for scan type selection...")
            self.clear_images()

    def display_covers_for_region(self, selected_region: str, selected_scan_type: str = None):
        #Display covers for selected region and scan type-
        self.stop_image_loaders()
        self.clear_images()

        if not hasattr(self, 'cover_groups') or not selected_region:
            print("No cover groups available or no region selected")
            return

        print(f"\nDisplaying covers for region: {selected_region}, scan type: {selected_scan_type}")

        # Find cover group for selected region
        filtered_covers = []
        for group in self.cover_groups:
            countries = group.get('countries', [])
            if selected_region in countries:
                covers = group.get('covers', [])
                print(f"Found {len(covers)} covers in group with countries: {countries}")
                for cover in covers:
                    # Filter by scan type if specified
                    if selected_scan_type and cover.get('scan_of') != selected_scan_type:
                        continue
                    cover['countries'] = countries  # Add countries to each cover
                    filtered_covers.append(cover)

        print(f"Total matching covers found: {len(filtered_covers)}")

        # Display filtered covers
        cols = 6
        for i, cover in enumerate(filtered_covers):
            regions = cover.get('countries', ['Unknown Region'])
            region_str = ', '.join(regions)
            scan_type = cover.get('scan_of', 'Cover')

            print(f"Processing cover {i+1}: {scan_type} for {region_str}")

            image_widget = ImageWidget(
                image_url=cover.get('image', ''),
                image_type=scan_type,
                region=region_str
            )

            row = i // cols
            col = i % cols
            self.image_layout.addWidget(image_widget, row, col)

            # Start loading the image
            loader = ImageLoader(cover['image'], cover['image'])
            loader.image_loaded.connect(
                lambda f, p, w=image_widget: self.on_image_loaded_new(f, p, w))
            self.image_loaders.append(loader)
            loader.start()

        # Show message if no covers found
        if not filtered_covers:
            message = f"No covers found for region {selected_region}"
            if selected_scan_type:
                message += f" and type {selected_scan_type}"
            print(message)
            no_covers_label = QLabel(message)
            no_covers_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_covers_label.setStyleSheet("color: gray; padding: 20px;")
            self.image_layout.addWidget(no_covers_label, 0, 0)
            
    def refresh_cache(self):
        #Clear the cache directory and reload data
        try:
            import shutil
            cache_dir = self.api.config.cache_dir
            if os.path.exists(cache_dir):
                shutil.rmtree(cache_dir)
            os.makedirs(cache_dir)

            # Reload current view
            self.load_platforms()
            QMessageBox.information(self, "Success", "Cache refreshed successfully")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to refresh cache: {str(e)}")

    def clear_images(self):
        #Clear images and stop loaders
        self.stop_image_loaders()
        while self.image_layout.count():
            item = self.image_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def clear_game_details(self):
        #Clear all game details displays
        for label in self.details_labels.values():
            label.setText("")

    def load_game_details(self):
        #Load game covers
        if not hasattr(self, 'selected_game_id'):
            return

        try:
            progress = QProgressDialog("Loading game covers...", "Cancel", 0, 100, self)
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.setAutoClose(True)
            progress.setValue(0)

            # Get platform ID for current platform
            platform_id = self.platforms[self.platform_combo.currentText()]

            print(f"\nLoading covers for game ID: {self.selected_game_id} on platform: {platform_id}")

            # Load cover images for specific platform
            covers_response = self.api.get_game_platform_covers(self.selected_game_id, platform_id)
            print(f"Received cover groups: {len(covers_response.get('cover_groups', []))}")

            progress.setValue(50)

            # Update the name label with just the game title
            game_title = next(g for g in self.current_games if g['game_id'] == self.selected_game_id)['title']
            self.details_labels['Name'].setText(f"Name: {game_title}")

            # Populate regions and scan types
            self.populate_regions(covers_response)
            self.populate_scan_types(covers_response)

            # Clear any existing images
            self.clear_images()

            progress.setValue(100)
            
        except Exception as e:
            print(f"Error loading game details: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to load game covers: {str(e)}")
            
    def on_scan_type_changed(self, scan_type: str):
        # Handle scan type selection change
        if scan_type == "Select cover type...":
            return

        print(f"\nScan type changed to: {scan_type}")
        if hasattr(self, 'cover_groups') and self.region_code_combo.currentText():
            self.display_covers_for_region(self.region_code_combo.currentText(), scan_type)

    def on_image_loaded_new(self, filename, pixmap, widget):
        # Handle loaded image for existing widget
        if widget:
            # Scale pixmap to fit the label while maintaining aspect ratio
            scaled_pixmap = pixmap.scaled(
                widget.image_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            widget.image_label.setPixmap(scaled_pixmap)

    def on_game_selected(self, display_text: str):
        # Handle game selection from search results
        if not display_text or display_text in ["Searching...", "No games found"]:
            return
    
        try:
            # Get the current index and retrieve the stored game ID
            current_text = self.game_results_combo.currentText()
            game_id_str = current_text.split("(ID: ")[-1].rstrip(")")  # Extract ID from display text
            
            # Find selected game from current_games using the game ID
            game = next(g for g in self.current_games if str(g['game_id']) == game_id_str)
            self.selected_game_id = game['game_id']
    
            print(f"Selected game ID: {self.selected_game_id}")
    
            # Clear previous details/images
            self.clear_game_details()
            self.clear_images()
    
            # Load and display game details and covers
            self.load_game_details()
    
        except Exception as e:
            print(f"Error in game selection: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to select game: {str(e)}")

    def search_games(self):
        # Handle game search
        search_term = self.game_search.text().strip()
        platform_name = self.platform_combo.currentText()

        if not search_term or not platform_name:
            return

        try:
            platform_id = self.platforms[platform_name]

            # Show searching indicator
            self.game_results_combo.clear()
            self.game_results_combo.addItem("Searching...")
            self.game_results_combo.setVisible(True)

            # Get search results
            search_results = self.api.search_games_by_platform(platform_id, search_term)

            # Update results combo
            self.game_results_combo.clear()
            if not search_results:
                self.game_results_combo.addItem("No games found")
            else:
                # Store the full game data
                self.current_games = search_results

                # Add titles with game IDs to combo
                for game in search_results:
                    display_text = f"{game['title']} (ID: {game['game_id']})"
                    # Store the game ID in the item's user data
                    self.game_results_combo.addItem(display_text, game['game_id'])

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to search games: {str(e)}")
            self.game_results_combo.setVisible(False)

    def export_to_csv(self):
        def get_existing_quantity(inventory_rows, handle, variant):
            # Get existing quantity for a specific variant
            for row in inventory_rows:
                if row['Handle'] == handle and row['Option1 Value'] == variant:
                    return int(row.get('Available', '0'))
            return 0
        # Export product and inventory data to CSV
        if not self.game_results_combo.currentText():
            QMessageBox.warning(self, "Warning", "Please select a game first")
            return

        try:
            # Get selected image URL or custom URL
            selected_image_url = None
            for i in range(self.image_layout.count()):
                widget = self.image_layout.itemAt(i).widget()
                if isinstance(widget, ImageWidget) and widget.checkbox.isChecked():
                    selected_image_url = widget.image_url
                    break

            # If no image selected, check for custom URL
            if not selected_image_url:
                custom_url = self.custom_image_url.text().strip()
                if custom_url:
                    selected_image_url = custom_url
                else:
                    QMessageBox.warning(self, "Warning", "Please select an image or provide a custom image URL")
                    return

            # Get location and quantity for inventory
            location = self.location_input.text().strip()
            if not location:
                QMessageBox.warning(self, "Warning", "Please enter a location")
                return

            try:
                quantity = int(self.quantity_input.text() or "0")
            except ValueError:
                QMessageBox.warning(self, "Warning", "Please enter a valid quantity")
                return

            # Get current game data using game ID
            current_text = self.game_results_combo.currentText()
            game_id_str = current_text.split("(ID: ")[-1].rstrip(")")  # Extract ID from display text
            game = next(g for g in self.current_games if str(g['game_id']) == game_id_str)

            # Get region code and platform
            region_code = self.custom_region_input.text().strip() or self.region_code_combo.currentText()
            platform_name = self.platform_combo.currentText()

            # Create handle (slug)
            handle = f"{game['title']}-{platform_name}-{region_code}".lower()
            handle = handle.replace(' ', '-').replace('&', 'and')
            handle = ''.join(c for c in handle if c.isalnum() or c == '-')

            # Function to read existing CSV into memory
            def read_csv_to_list(filename):
                if not os.path.exists(filename):
                    return []
                with open(filename, 'r', newline='', encoding='utf-8') as f:
                    return list(csv.DictReader(f))

            # Read existing CSVs
            product_rows = read_csv_to_list('product_import.csv')
            inventory_rows = read_csv_to_list('inventory_import.csv')

            # Find and remove existing entries with the same handle
            product_rows = [row for row in product_rows if row['Handle'] != handle]
            inventory_rows = [row for row in inventory_rows if row['Handle'] != handle]

            # Create title with region code
            title = f"{game['title']} {platform_name} Game [{region_code}]"

            # Create product category
            product_category = "Software > Video Game Software"

            # Create tags
            base_tags = [game['title'], platform_name]
            if platform_name.lower() == "playstation 2":
                base_tags.extend(["PS2", "PlayStation2"])

            # Add custom tags
            custom_tags = [tag.strip() for tag in self.custom_tags_input.text().split(',') if tag.strip()]
            all_tags = base_tags + custom_tags
            tags = ', '.join(all_tags)

            # Create base row with all data
            base_row = {
                'Handle': handle,
                'Title': title,
                'Vendor': 'Trippy Trades',
                'Product Category': product_category,
                'Type': 'Video Games & Consoles: Video Games',
                'Tags': tags,
                'Published': 'false',
                'Option1 Name': 'Title',
                'Variant Grams': '150.0',
                'Variant Inventory Tracker': 'shopify',
                'Variant Inventory Policy': 'deny',
                'Variant Fulfillment Service': 'manual',
                'Variant Price': '0.00',
                'Variant Requires Shipping': 'true',
                'Variant Taxable': 'true',
                'Image Src': selected_image_url,
                'Image Position': '1',
                'SEO Title': title,
                'Variant Weight Unit': 'kg',
                'Included / Australia': 'true',
                'Included / new zealand': 'true',
                'Included / world wide': 'true',
                'Status': 'draft'
            }

            # Get selected variant
            selected_variant = self.variant_combo.currentText()

            # Prepare new product rows
            new_product_rows = []
            for i, variant in enumerate(self.variants):
                row = base_row.copy() if i == 0 else {
                    'Handle': handle,
                    'Option1 Value': variant,
                    'Variant Grams': '150.0',
                    'Variant Inventory Tracker': 'shopify',
                    'Variant Inventory Policy': 'deny',
                    'Variant Fulfillment Service': 'manual',
                    'Variant Price': '0.00',
                    'Variant Requires Shipping': 'true',
                    'Variant Taxable': 'true',
                    'Variant Weight Unit': 'kg'
                }

                if i == 0:  # First row gets the variant name too
                    row['Option1 Value'] = variant

                # Handle quotes for fields with commas
                processed_row = {}
                for key, value in row.items():
                    if isinstance(value, str):
                        if ',' in value and not (value.startswith('"') and value.endswith('"')):
                            processed_row[key] = f'"{value}"'
                        else:
                            processed_row[key] = value
                    else:
                        processed_row[key] = value

                new_product_rows.append(processed_row)

            # Prepare new inventory rows
            new_inventory_rows = []
            for variant in self.variants:
                # Get existing quantity for this variant
                existing_quantity = get_existing_quantity(inventory_rows, handle, variant)
                
                # Calculate new quantity (add to existing if this is the selected variant)
                new_quantity = existing_quantity
                if variant == selected_variant:
                    new_quantity += quantity
                
                row = {
                    'Handle': handle,
                    'Title': '',
                    'Option1 Name': 'Title',
                    'Option1 Value': variant,
                    'Option2 Name': '',
                    'Option2 Value': '',
                    'Option3 Name': '',
                    'Option3 Value': '',
                    'SKU': '',
                    'HS Code': '',
                    'COO': '',
                    'Location': location,
                    'Unavailable': '0',
                    'Committed': '0',
                    'Available': str(new_quantity),
                    'On hand': str(new_quantity)
                }
                new_inventory_rows.append(row)

            # Write updated product CSV
            with open('product_import.csv', 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
                writer.writeheader()
                writer.writerows(product_rows + new_product_rows)

            # Write updated inventory CSV
            inventory_fields = [
                'Handle', 'Title', 'Option1 Name', 'Option1 Value', 
                'Option2 Name', 'Option2 Value', 'Option3 Name', 'Option3 Value',
                'SKU', 'HS Code', 'COO', 'Location', 
                'Unavailable', 'Committed', 'Available', 'On hand'
            ]
            with open('inventory_import.csv', 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=inventory_fields)
                writer.writeheader()
                writer.writerows(inventory_rows + new_inventory_rows)

            # Show success message
            self.message_label.setText("Product and inventory data updated successfully!")
            self.message_label.setStyleSheet("color: green;")
            QTimer.singleShot(5000, lambda: self.message_label.setText(""))

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export: {str(e)}")

    def get_selected_variant(self) -> str:
        # Get the currently selected variant
        return self.variant_combo.currentText()

def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    # Apply a modern and sharp theme with better layout and hover colors for dropdowns
    app.setStyleSheet("""
        QMainWindow {
            background-color: #ffffff;
        }

        QLabel {
            color: #2c3e50;
            font-size: 16px;  # Larger font for clarity
            font-weight: bold;
            padding: 5px;
        }

        QPushButton {
            background-color: #dc34af;
            color: white;
            border-radius: 5px;
            padding: 10px;
            font-size: 15px;  # Slightly larger text
            border: none;
        }

        QPushButton:hover {
            background-color: #57a5d8;
        }

        QPushButton:pressed {
            background-color: #3498db;
        }

        QFrame {
            border: 2px solid #57a5d8;  # Thicker border for emphasis
            border-radius: 5px;
            background-color: #f0f0f0;
            margin: 15px;  # Increased margin for spacing
        }

        QCheckBox {
            color: #2c3e50;
            font-size: 14px;
        }

        QCheckBox::indicator {
            border: 2px solid #dc34af;  # Thicker indicator border
            width: 18px;
            height: 18px;
            background-color: #f0f0f0;
        }

        QCheckBox::indicator:checked {
            background-color: #57a5d8;
            border: 2px solid #57a5d8;
        }

        QComboBox {
            border: 1px solid #dc34af;
            background-color: #ffffff;
            padding: 8px;
            font-size: 14px;
        }

        QComboBox::drop-down {
            border: 0px;
        }

        QComboBox::item {
            color: #2c3e50;
            background-color: #ffffff;
        }

        QComboBox QAbstractItemView {
            border: 1px solid #57a5d8;
            selection-background-color: #dc34af;  # Background color when hovering or selecting
            selection-color: #ffffff;  # Text color when selecting
        }

        QLineEdit {
            border: 2px solid #57a5d8;
            padding: 8px;
            border-radius: 4px;
            font-size: 14px;
        }

        QDialog {
            background-color: #f0f0f0;
            border: 2px solid #dc34af;
        }

        QProgressDialog {
            background-color: #ffffff;
            border: 1px solid #dc34af;
            padding: 10px;
            font-size: 14px;
        }

        QMessageBox {
            background-color: #ffffff;
            border: 2px solid #57a5d8;
            padding: 10px;
        }

        QScrollArea {
            border: none;
            padding: 10px;
        }
    """)

    window = GameBrowser()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
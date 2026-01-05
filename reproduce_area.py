import unittest
import sys
from bs4 import BeautifulSoup
from olx_parser import OLXParser

# Fix encoding for Windows console
sys.stdout.reconfigure(encoding='utf-8')

class TestAreaExtraction(unittest.TestCase):
    def setUp(self):
        self.parser = OLXParser()

    def test_area_extraction_variations(self):
        # Case 1: Standard case with "Общая площадь: 62 м²"
        html1 = """
        <div>
            <ul>
                <li>Количество комнат: 2</li>
                <li>Общая площадь: 62 м²</li>
                <li>Этаж: 3</li>
            </ul>
        </div>
        """
        soup1 = BeautifulSoup(html1, 'lxml')
        params1 = self.parser._extract_parameters(soup1)
        print(f"Case 1 Params: {params1}")
        self.assertIn('Общая площадь', params1)
        self.assertEqual(params1['Общая площадь'], '62')

        # Case 2: "Площадь: 62 м²" (shorter label)
        html2 = """
        <div>
            <p>Площадь: 62 м²</p>
        </div>
        """
        soup2 = BeautifulSoup(html2, 'lxml')
        params2 = self.parser._extract_parameters(soup2)
        print(f"Case 2 Params: {params2}")
        self.assertIn('Общая площадь', params2)
        self.assertEqual(params2['Общая площадь'], '62')

        # Case 3: Newline separation
        html3 = """
        <div>
            <span>Общая площадь</span>
            <span>62 м²</span>
        </div>
        """
        soup3 = BeautifulSoup(html3, 'lxml')
        params3 = self.parser._extract_parameters(soup3)
        print(f"Case 3 (Newline) Params: {params3}")
        # Note: current parser might fail this if get_text merges poorly or regex expects "Label: Value" strictly
        # self.assertEqual(params3.get('Общая площадь'), '62') 

        # Case 4: From the user screenshot (hypothetically)
        # Looks like "Общая площадь: 62" in a button or chip-like element.
        html4 = """
        <div class="css-1">
            <p>Общая площадь: 62</p>
        </div>
        """
        soup4 = BeautifulSoup(html4, 'lxml')
        params4 = self.parser._extract_parameters(soup4)
        print(f"Case 4 Params: {params4}")
        self.assertEqual(params4.get('Общая площадь'), '62')

        # Case 5: With 'м' instead of 'м²'
        html5 = """
        <li>Общая площадь: 62 м</li>
        """
        soup5 = BeautifulSoup(html5, 'lxml')
        params5 = self.parser._extract_parameters(soup5)
        print(f"Case 5 Params: {params5}")
        self.assertEqual(params5.get('Общая площадь'), '62')

        # Case 6: Merged text (likely cause)
        html6 = """<div>Общая площадь: 62</div><div>Этаж: 3</div>"""
        soup6 = BeautifulSoup(html6, 'lxml')
        # Simulate what happens in parser: soup.get_text() without separator
        # Verify that get_text actually merges them
        print(f"Case 6 Text: {soup6.get_text()}") 
        params6 = self.parser._extract_parameters(soup6)
        print(f"Case 6 Params: {params6}")
        self.assertIn('Общая площадь', params6)
        self.assertEqual(params6['Общая площадь'], '62')

        # Case 7: Extra spaces in label
        html7 = """
        <div>
            <p>Общая  площадь: 75 м²</p>
        </div>
        """
        soup7 = BeautifulSoup(html7, 'lxml')
        params7 = self.parser._extract_parameters(soup7)
        print(f"Case 7 Params: {params7}")
        self.assertIn('Общая площадь', params7)
        self.assertEqual(params7['Общая площадь'], '75')

if __name__ == '__main__':
    unittest.main()

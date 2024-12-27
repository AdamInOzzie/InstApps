
"""Service for handling CHARTS functionality."""
import logging
import streamlit as st
import pandas as pd
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

class ChartsService:
    @staticmethod
    def handle_charts(sheet_names: List[str], sheet_id: str, sheets_client) -> None:
        """Handle the CHARTS sheet functionality."""
        try:
            # Show Charts dropdown if CHARTS sheet exists
            if 'CHARTS' in sheet_names:
                try:
                    charts_df = sheets_client.read_sheet_data(sheet_id, 'CHARTS')
                    if not charts_df.empty:
                        chart_column = next((col for col in ['ChartName', 'CHARTNAME'] 
                                          if col in charts_df.columns), None)
                        
                        if chart_column:
                            chart_names = charts_df[chart_column].dropna().tolist()
                            if chart_names:
                                st.markdown("### 📊 Chart Selection")
                                selected_chart = st.selectbox(
                                    "Select a chart to view",
                                    options=chart_names,
                                    key=f'chart_selector_{sheet_id}',
                                    label_visibility="collapsed"
                                )
                                
                                compute_button = st.button(
                                    "Display Chart",
                                    key=f"compute_chart_{sheet_id}"
                                )

                                # Only proceed if chart is selected and button is clicked
                                if selected_chart and compute_button:
                                    chart_row = charts_df[charts_df[chart_column] == selected_chart].iloc[0]
                                    
                                    # Handle BAR chart computation
                                    if chart_row['TYPE'].lower() in ['bar', 'bar chart']:
                                        inputs_df = sheets_client.read_sheet_data(sheet_id, 'INPUTS')
                                        input_field_row = inputs_df[inputs_df['Name'] == chart_row['INPUT']]
                                        
                                        if not input_field_row.empty:
                                            original_value = input_field_row['Value'].iloc[0]
                                            input_values = []
                                            output1_values = []
                                            output2_values = []
                                            
                                            current_value = float(chart_row['INPUT LOW'])
                                            while current_value <= float(chart_row['INPUT HIGH']):
                                                from services.spreadsheet_service import SpreadsheetService
                                                spreadsheet_service = SpreadsheetService(sheets_client)
                                                input_row = input_field_row.index[0] + 2
                                                spreadsheet_service.update_input_cell(sheet_id, str(current_value), input_row)
                                                
                                                import time
                                                time.sleep(1.0)
                                                
                                                outputs_df = sheets_client.read_sheet_data(sheet_id, 'OUTPUTS')
                                                output1_row = outputs_df[outputs_df['Name'] == chart_row['OUTPUT1']]
                                                if not output1_row.empty:
                                                    input_values.append(current_value)
                                                    output1_values.append(output1_row['Value'].iloc[0])
                                                    
                                                    if chart_row['OUTPUT2']:
                                                        output2_row = outputs_df[outputs_df['Name'] == chart_row['OUTPUT2']]
                                                        if not output2_row.empty:
                                                            output2_values.append(output2_row['Value'].iloc[0])
                                                
                                                current_value += float(chart_row['INPUT STEP'])
                                            
                                            # Reset to original value
                                            spreadsheet_service.update_input_cell(sheet_id, str(original_value), input_row)
                                            
                                            # Display results
                                            results = {'Input': input_values, 'Output1': output1_values}
                                            if output2_values:
                                                results['Output2'] = output2_values
                                            df = pd.DataFrame(results)
                                            df.columns = [chart_row['INPUT'], chart_row['OUTPUT1']] + ([chart_row['OUTPUT2']] if output2_values else [])
                                            
                                            # Show table
                                            st.dataframe(df, hide_index=True)
                                            
                                            # Create bar chart
                                            st.markdown("### Bar Chart View")
                                            chart_data = pd.DataFrame({
                                                'Input': input_values,
                                                chart_row['OUTPUT1']: output1_values,
                                                **({chart_row['OUTPUT2']: output2_values} if output2_values else {})
                                            })
                                            chart_data.index = chart_data['Input'].round(1)
                                            st.bar_chart(
                                                data=chart_data.drop('Input', axis=1),
                                                height=400,
                                                use_container_width=True
                                            )
                                    
                except Exception as e:
                    logger.error(f"Error loading CHARTS: {str(e)}")
                    raise
                    
        except Exception as e:
            logger.error(f"Error handling charts: {str(e)}")
            st.error(f"Error displaying charts: {str(e)}")

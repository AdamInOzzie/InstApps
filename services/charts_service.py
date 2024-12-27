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
                                
                                # Create two columns with 4:1 ratio
                                col1, col2 = st.columns([4, 1])
                                
                                with col1:
                                    selected_chart = st.selectbox(
                                        "Select a chart to view",
                                        options=chart_names,
                                        key=f'chart_selector_{sheet_id}',
                                        label_visibility="collapsed"
                                    )
                                
                                with col2:
                                    compute_button = st.button(
                                        "Display Chart",
                                        key=f"compute_chart_{sheet_id}"
                                    )

                                # Only proceed if chart is selected and button is clicked
                                if selected_chart and compute_button:
                                    chart_row = charts_df[charts_df[chart_column] == selected_chart].iloc[0]
                                    st.session_state.current_chart = {
                                        'name': selected_chart,
                                        'type': chart_row['TYPE'],
                                        'input': chart_row['INPUT'],
                                        'input_low': float(chart_row['INPUT LOW']),
                                        'input_high': float(chart_row['INPUT HIGH']),
                                        'input_step': float(chart_row['INPUT STEP']),
                                        'output1': chart_row['OUTPUT1'],
                                        'output2': chart_row['OUTPUT2'],
                                        'x_axis_low': float(chart_row['X AXIS Low']),
                                        'x_axis_high': float(chart_row['X AXIS HIGH'])
                                    }

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
                                                success = spreadsheet_service.update_input_cell(sheet_id, str(current_value), input_row)
                                                
                                                if not success:
                                                    logger.error(f"Failed to update input cell with value {current_value}")
                                                    break
                                                
                                                import time
                                                time.sleep(1.0)
                                                
                                                try:
                                                    outputs_df = sheets_client.read_sheet_data(sheet_id, 'OUTPUTS')
                                                    if outputs_df is None or outputs_df.empty:
                                                        logger.error("Empty outputs dataframe")
                                                        continue
                                                    
                                                    output1_row = outputs_df[outputs_df['Name'] == chart_row['OUTPUT1']]
                                                    if not output1_row.empty:
                                                        input_values.append(current_value)
                                                        output1_values.append(output1_row['Value'].iloc[0])
                                                        
                                                        if chart_row['OUTPUT2']:
                                                            output2_row = outputs_df[outputs_df['Name'] == chart_row['OUTPUT2']]
                                                            if not output2_row.empty:
                                                                output2_values.append(output2_row['Value'].iloc[0])
                                                    
                                                    del outputs_df
                                                    
                                                except Exception as e:
                                                    logger.error(f"Error processing outputs: {str(e)}")
                                                    continue
                                                    
                                                current_value += float(chart_row['INPUT STEP'])
                                            
                                            # Reset to original value
                                            spreadsheet_service.update_input_cell(sheet_id, str(original_value), input_row)
                                            
                                            # Create placeholder for table
                                            table_placeholder = st.empty()
                                            
                                            # Initial display
                                            results = {'Input': input_values, 'Output1': output1_values}
                                            if output2_values:
                                                results['Output2'] = output2_values
                                            df = pd.DataFrame(results)
                                            df.columns = [chart_row['INPUT'], chart_row['OUTPUT1']] + ([chart_row['OUTPUT2']] if output2_values else [])
                                            
                                            # Display both table and chart for BAR type
                                            if chart_row['TYPE'].lower() in ['bar', 'bar chart']:
                                                # Show table above chart
                                                table_placeholder.dataframe(df, hide_index=True)
                                                
                                                # Create bar chart
                                                st.markdown("### Bar Chart View")
                                                chart_data = pd.DataFrame({
                                                    'Input': input_values,
                                                    chart_row['OUTPUT1']: output1_values,
                                                    **({chart_row['OUTPUT2']: output2_values} if output2_values else {})
                                                })
                                                st.bar_chart(
                                                    chart_data.set_index('Input'),
                                                    height=400
                                                )
                                            else:
                                                # For non-bar charts, just show table
                                                table_placeholder.dataframe(df, hide_index=True)
                                    
                except Exception as e:
                    logger.error(f"Error loading CHARTS: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Error handling charts: {str(e)}")
            st.error(f"Error displaying charts: {str(e)}")
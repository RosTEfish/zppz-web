const formatNumber = (value: number) => value.toLocaleString("zh-CN");

export const dataGridZhCN = {
  noRowsLabel: "没有数据。",
  noResultsOverlayLabel: "未找到数据。",
  noColumnsOverlayLabel: "没有列",
  noColumnsOverlayManageColumns: "管理列",
  toolbarDensity: "表格密度",
  toolbarDensityLabel: "表格密度",
  toolbarDensityCompact: "紧密",
  toolbarDensityStandard: "标准",
  toolbarDensityComfortable: "稀疏",
  toolbarColumns: "列",
  toolbarColumnsLabel: "选择列",
  toolbarFilters: "筛选器",
  toolbarFiltersLabel: "显示筛选器",
  toolbarFiltersTooltipHide: "隐藏筛选器",
  toolbarFiltersTooltipShow: "显示筛选器",
  toolbarFiltersTooltipActive: (count: number) => `${count} 个筛选器`,
  toolbarQuickFilterPlaceholder: "搜索…",
  toolbarQuickFilterLabel: "搜索",
  toolbarQuickFilterDeleteIconLabel: "清除",
  toolbarExport: "导出",
  toolbarExportLabel: "导出",
  toolbarExportCSV: "导出至CSV",
  toolbarExportPrint: "打印",
  toolbarExportExcel: "导出至Excel",
  columnsManagementSearchTitle: "搜索",
  columnsManagementNoColumns: "没有列",
  columnsManagementShowHideAllText: "显示/隐藏所有",
  columnsManagementReset: "重置",
  columnsManagementDeleteIconLabel: "清除",
  filterPanelAddFilter: "添加筛选器",
  filterPanelRemoveAll: "清除全部",
  filterPanelDeleteIconLabel: "删除",
  filterPanelLogicOperator: "逻辑操作器",
  filterPanelOperator: "操作器",
  filterPanelOperatorAnd: "与",
  filterPanelOperatorOr: "或",
  filterPanelColumn: "列",
  filterPanelInputLabel: "值",
  filterPanelInputPlaceholder: "筛选值",
  filterOperatorContains: "包含",
  filterOperatorDoesNotContain: "不包含",
  filterOperatorEquals: "等于",
  filterOperatorDoesNotEqual: "不等于",
  filterOperatorStartsWith: "开始于",
  filterOperatorEndsWith: "结束于",
  filterOperatorIs: "是",
  filterOperatorNot: "不是",
  filterOperatorAfter: "在后面",
  filterOperatorOnOrAfter: "正在后面",
  filterOperatorBefore: "在前面",
  filterOperatorOnOrBefore: "正在前面",
  filterOperatorIsEmpty: "为空",
  filterOperatorIsNotEmpty: "不为空",
  filterOperatorIsAnyOf: "属于",
  "filterOperator=": "=",
  "filterOperator!=": "!=",
  "filterOperator>": ">",
  "filterOperator>=": ">=",
  "filterOperator<": "<",
  "filterOperator<=": "<=",
  columnMenuLabel: "菜单",
  columnMenuAriaLabel: (columnName: string) => `${columnName} 列菜单`,
  columnMenuShowColumns: "显示",
  columnMenuManageColumns: "管理列",
  columnMenuFilter: "筛选器",
  columnMenuHideColumn: "隐藏",
  columnMenuUnsort: "恢复默认",
  columnMenuSortAsc: "升序",
  columnMenuSortDesc: "降序",
  columnHeaderFiltersTooltipActive: (count: number) => `${count} 个筛选器`,
  columnHeaderFiltersLabel: "显示筛选器",
  columnHeaderSortIconLabel: "排序",
  footerRowSelected: (count: number) => `共选中了${count.toLocaleString()}行`,
  footerTotalRows: "所有行:",
  footerTotalVisibleRows: (visibleCount: number, totalCount: number) =>
    `${visibleCount.toLocaleString()} / ${totalCount.toLocaleString()}`,
  checkboxSelectionHeaderName: "多选框",
  checkboxSelectionSelectAllRows: "全选行",
  checkboxSelectionUnselectAllRows: "反选所有行",
  checkboxSelectionSelectRow: "选择行",
  checkboxSelectionUnselectRow: "反选行",
  paginationRowsPerPage: "每页行数:",
  paginationDisplayedRows: ({
    from,
    to,
    count,
    estimated,
  }: {
    from: number;
    to: number;
    count: number;
    estimated?: number;
  }) => {
    if (!estimated) {
      return `${formatNumber(from)}–${formatNumber(to)} 共 ${count !== -1 ? formatNumber(count) : `超过 ${formatNumber(to)}`}`;
    }
    const estimatedLabel = estimated && estimated > to ? `约 ${formatNumber(estimated)}` : `超过 ${formatNumber(to)}`;
    return `${formatNumber(from)}–${formatNumber(to)} 共 ${count !== -1 ? formatNumber(count) : estimatedLabel}`;
  },
  paginationItemAriaLabel: (type: "first" | "last" | "next" | "previous") => {
    if (type === "first") return "第一页";
    if (type === "last") return "最后一页";
    if (type === "next") return "下一页";
    return "上一页";
  },
};

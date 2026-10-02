# ERP Delivery Management — Technical Decisions

Tài liệu này ghi nhận các quyết định kiến trúc đã được người dùng yêu cầu chuẩn hóa ngày 2026-10-02. Đây là target design; trạng thái triển khai phải được xác minh riêng trong code và tests.

### ADR-001 Mở rộng `project.project` thay vì tạo model dự án song song

- **Ngày ghi nhận**: 2026-10-02
- **Phạm vi module**: `erp_delivery_management`
- **Bối cảnh và Vấn đề**: Bài toán cần dùng Project, Task và Milestone chuẩn của Odoo nhưng mô tả ban đầu để mở lựa chọn giữa `project.project` và `erp.project`.
- **Quyết định Kỹ thuật**: Mở rộng `project.project`, đánh dấu ERP project bằng `is_erp_project`; mở rộng `project.task` và `project.milestone` cho dữ liệu delivery.
- **Các phương án thay thế đã loại bỏ**: Model `erp.project` riêng bị loại vì tạo luồng project song song, phải đồng bộ task/milestone và làm tăng security/view/reporting duplication.
- **Hệ quả và Trade-off**:
  - Ưu điểm: Tận dụng framework chuẩn, navigation và security sẵn có; ít dữ liệu trùng.
  - Điểm cần lưu ý: Custom constraint/compute phải chỉ áp dụng cho ERP project để không ảnh hưởng project thông thường.

### ADR-002 Ba addon và ownership độc lập

- **Ngày ghi nhận**: 2026-10-02
- **Phạm vi module**: `erp_delivery_management`, `erp_delivery_sale`, `erp_delivery_quality`
- **Bối cảnh và Vấn đề**: Sales và Quality phải cài độc lập, toàn bộ bài chỉ được có tối đa ba custom addons.
- **Quyết định Kỹ thuật**: Core không phụ thuộc addon tùy chọn; Sales và Quality chỉ phụ thuộc Core. Field, view và XML ID của mỗi tích hợp thuộc chính addon đó.
- **Các phương án thay thế đã loại bỏ**: Addon cầu nối Sales+Quality thứ tư vi phạm giới hạn; Quality phụ thuộc Sales làm mất khả năng cài độc lập.
- **Hệ quả và Trade-off**:
  - Ưu điểm: Dependency graph ổn định, gỡ/cài addon tùy chọn an toàn.
  - Điểm cần lưu ý: Nghiệp vụ chỉ xuất hiện khi hai addon cùng có mặt phải được tổ chức bằng hook runtime mà không tham chiếu XML chéo.

### ADR-003 Go-live blockers dùng cooperative inheritance

- **Ngày ghi nhận**: 2026-10-02
- **Phạm vi module**: cả ba addon
- **Bối cảnh và Vấn đề**: Nhiều addon cùng mở rộng Go-live; override raise sớm có thể che logic hoặc phụ thuộc MRO.
- **Quyết định Kỹ thuật**: Core cung cấp `_get_go_live_blockers()` trả danh sách. Mỗi addon gọi `super()`, append blocker và trả lại. `action_go_live()` tổng hợp rồi raise một lần.
- **Các phương án thay thế đã loại bỏ**: Quality dò `sale_order_id` trong registry tạo coupling ngầm; mỗi addon override action toàn phần dễ làm mất logic của addon khác.
- **Hệ quả và Trade-off**:
  - Ưu điểm: Có thể kiểm thử từng blocker và hiển thị nhiều lý do cùng lúc; không phụ thuộc thứ tự cài đặt.
  - Điểm cần lưu ý: Tất cả override phải tuân thủ `super()` và không mutate record trước khi blocker rỗng.

### ADR-004 Điều kiện thương mại thuộc Sales Integration

- **Ngày ghi nhận**: 2026-10-02
- **Phạm vi module**: `erp_delivery_sale`
- **Bối cảnh và Vấn đề**: Đề nhấn mạnh kiểm tra thương mại khi Sales và Quality cùng cài, nhưng Quality không được phụ thuộc Sales.
- **Quyết định Kỹ thuật**: Khi Sales Integration được cài và project có order liên kết, order phải ở state `sale` để Go-live. Odoo 18 Community không có state `done` trên `sale.order`. Khi Quality cũng được cài, cả hai blocker tự động được hợp qua hook.
- **Các phương án thay thế đã loại bỏ**: Chỉ chạy kiểm tra thương mại từ Quality khi phát hiện field Sales bị loại vì coupling và khó khai báo view/dependency đúng.
- **Hệ quả và Trade-off**:
  - Ưu điểm: Rule thương mại nhất quán cả khi Sales chạy độc lập.
  - Điểm cần lưu ý: Đây là assumption chặt hơn mức tối thiểu của đề và phải được nêu trong README.

### ADR-005 Milestone dùng model chuẩn riêng

- **Ngày ghi nhận**: 2026-10-02
- **Phạm vi module**: `erp_delivery_management`
- **Bối cảnh và Vấn đề**: Odoo 18 dùng `project.milestone`; mô tả cũ gộp task/milestone dưới `project.task`.
- **Quyết định Kỹ thuật**: Mở rộng `project.milestone` với mandatory, risk và project line. Completion dùng `is_reached`.
- **Các phương án thay thế đã loại bỏ**: Mô phỏng milestone bằng task làm sai UX chuẩn và semantics `deadline/is_reached`.
- **Hệ quả và Trade-off**:
  - Ưu điểm: Tương thích Project chuẩn và kiểm tra Go-live đúng đối tượng.
  - Điểm cần lưu ý: Aggregate/blocker phải gộp hai nguồn task và milestone theo batch.

### ADR-006 Stored health có cron theo ngày

- **Ngày ghi nhận**: 2026-10-02
- **Phạm vi module**: `erp_delivery_management`
- **Bối cảnh và Vấn đề**: `health_state` cần store/index để search/group nhưng phụ thuộc ngày hiện tại, không tự recompute khi thời gian trôi.
- **Quyết định Kỹ thuật**: Lưu `health_state`, recompute theo source writes và cron daily cho project đang hoạt động. Cron xử lý batch/chunk.
- **Các phương án thay thế đã loại bỏ**: Non-stored field làm search/group đắt; chỉ `@api.depends` khiến trạng thái cũ khi không có write.
- **Hệ quả và Trade-off**:
  - Ưu điểm: List/search nhanh và dữ liệu tự cập nhật theo lịch.
  - Điểm cần lưu ý: Có độ trễ tối đa theo lịch cron và thêm chi phí recompute hằng ngày.

### ADR-007 Duration dùng chênh lệch ngày và từ chối payload mâu thuẫn

- **Ngày ghi nhận**: 2026-10-02
- **Phạm vi module**: `erp_delivery_management`
- **Bối cảnh và Vấn đề**: Duration vừa compute từ hai ngày vừa cho phép nhập trực tiếp.
- **Quyết định Kỹ thuật**: Duration bằng planned date trừ start date; inverse cộng duration vào start. Payload gửi cả duration và planned date không nhất quán bị từ chối. Onchange chỉ phục vụ UI.
- **Các phương án thay thế đã loại bỏ**: Âm thầm ưu tiên một field gây kết quả khác nhau giữa UI và RPC; inclusive day count trái ví dụ nghiệm thu.
- **Hệ quả và Trade-off**:
  - Ưu điểm: Semantics xác định, test được và không phụ thuộc thứ tự vals.
  - Điểm cần lưu ý: Client tích hợp phải gửi dữ liệu nhất quán nếu gửi cả hai field.

### ADR-008 Một nguồn liên kết Sales Order và database uniqueness

- **Ngày ghi nhận**: 2026-10-02
- **Phạm vi module**: `erp_delivery_sale`
- **Bối cảnh và Vấn đề**: Hai chiều navigation dễ dẫn đến hai khóa ngoại lệch nhau; check-before-create không chống race condition.
- **Quyết định Kỹ thuật**: `project.project.sale_order_id` là nguồn duy nhất và unique khi có giá trị. Sale Order tìm project theo field này; smart button không cần khóa ngoại độc lập.
- **Các phương án thay thế đã loại bỏ**: Lưu cả `sale.order.project_id` và `project.sale_order_id`; chỉ search trước khi create.
- **Hệ quả và Trade-off**:
  - Ưu điểm: Không có đồng bộ hai chiều thủ công và chống duplicate ở database.
  - Điểm cần lưu ý: Reverse count/search cần triển khai batch-safe và index `sale_order_id`.

### ADR-009 Quality score có component cố định và audit snapshot

- **Ngày ghi nhận**: 2026-10-02
- **Phạm vi module**: `erp_delivery_quality`
- **Bối cảnh và Vấn đề**: Mô tả cũ nêu yếu tố tính điểm nhưng không có công thức, threshold storage hay lịch sử đánh giá.
- **Quyết định Kỹ thuật**: Điểm task/risk/module acceptance/checklist lần lượt tối đa 50/20/20/10; threshold theo company. Project giữ điểm hiện hành, `erp.quality.gate` giữ snapshot mỗi lần đánh giá.
- **Các phương án thay thế đã loại bỏ**: Hard-code duy nhất 80 và không lưu lịch sử; tin gate cũ mà không tính lại trước Go-live.
- **Hệ quả và Trade-off**:
  - Ưu điểm: Công thức xác định, audit được, hỗ trợ multi-company.
  - Điểm cần lưu ý: Thay đổi trọng số về sau cần migration/versioning để giải thích snapshot lịch sử.

### ADR-010 Field security theo group hierarchy

- **Ngày ghi nhận**: 2026-10-02
- **Phạm vi module**: cả ba addon
- **Bối cảnh và Vấn đề**: Ẩn field ở view không ngăn RPC/export; ACL nhiều group được hợp quyền.
- **Quyết định Kỹ thuật**: Manager implies Consultant, Consultant implies User. Internal cost/subscription là Manager-only; contract value/line price/internal notes là Consultant-or-Manager bằng Python field groups. Vì record rules chuẩn của Project cho internal user có thể cấp quyền đọc project công khai và các group rules được OR, một global rule chỉ áp dụng ERP records phải thu hẹp Consultant về PM/team nhưng miễn restriction assignment cho Manager.
- **Các phương án thay thế đã loại bỏ**: Chỉ dùng XML groups/invisible hoặc record rule để bảo vệ từng field.
- **Hệ quả và Trade-off**:
  - Ưu điểm: Chặn đọc qua ORM/RPC/export.
  - Điểm cần lưu ý: Compute/search/view của user thấp quyền không được vô tình tham chiếu field bị hạn chế; tests phải bao gồm ERP project public nhưng Consultant không được phân công.

### ADR-011 Giá trị hợp đồng giữ nguyên tiền tệ nguồn

- **Ngày ghi nhận**: 2026-10-02
- **Phạm vi module**: `erp_delivery_management`, `erp_delivery_sale`
- **Bối cảnh và Vấn đề**: `project.currency_id` chuẩn phản ánh tiền tệ công ty, trong khi Sales Order có thể dùng ngoại tệ. Sao chép `amount_total` nhưng hiển thị bằng tiền tệ công ty sẽ làm sai ý nghĩa snapshot thương mại.
- **Quyết định Kỹ thuật**: Core cung cấp `contract_currency_id` độc lập, mặc định theo công ty và làm currency field của `contract_value`. Sales snapshot đồng thời `amount_total` và `currency_id` của đơn hàng; đồng bộ về sau chỉ thực hiện qua action có tracking.
- **Các phương án thay thế đã loại bỏ**: Ghi trực tiếp số tiền ngoại tệ dưới `project.currency_id`; tự động quy đổi nhưng không lưu tỷ giá/số tiền nguồn; âm thầm đồng bộ lại mỗi khi đơn hàng đổi.
- **Hệ quả và Trade-off**:
  - Ưu điểm: Snapshot giữ đúng số tiền và đơn vị tiền của hợp đồng nguồn, kể cả đơn ngoại tệ.
  - Điểm cần lưu ý: Báo cáo hợp nhất theo tiền tệ công ty phải thực hiện quy đổi tường minh tại ngày báo cáo hoặc ngày hợp đồng.

### ADR-012 Định dạng chi phí nội bộ đa công ty bằng Float thay vì Monetary

- **Ngày ghi nhận**: 2026-10-02
- **Phạm vi module**: `erp_delivery_management`
- **Bối cảnh và Vấn đề**: `internal_cost` và `internal_cost_currency_id` trên `erp.solution` được yêu cầu là dữ liệu phụ thuộc công ty (`company_dependent=True`). Tuy nhiên, lõi Odoo 18 ORM chỉ cho phép danh sách kiểu dữ liệu nhất định làm `company_dependent` và không hỗ trợ `fields.Monetary`. Khai báo `fields.Monetary` kèm `company_dependent=True` hoặc `fields.Many2one` có `required=True` sẽ phát cảnh báo `UserWarning`.
- **Quyết định Kỹ thuật**:
  - Định nghĩa `internal_cost` bằng `fields.Float` với `company_dependent=True` và `digits="Product Price"`.
  - Định nghĩa `internal_cost_currency_id` bằng `fields.Many2one("res.currency")` với `company_dependent=True`, loại bỏ thuộc tính `required=True`.
  - Trên view XML, khai báo `widget="monetary"` kèm `options="{'currency_field': 'internal_cost_currency_id'}"` để giao diện hiển thị tiền tệ đầy đủ ký hiệu và định dạng.
- **Các phương án thay thế đã loại bỏ**:
  - Giữ `fields.Monetary` kèm `company_dependent=True`: Vi phạm quy chuẩn Odoo ORM và phát sinh cảnh báo hệ thống.
  - Tạo model quan hệ riêng để lưu chi phí theo company: Gây phức tạp hóa mô hình dữ liệu không cần thiết, đi ngược lại thiết kế `company_dependent` chuẩn mực của Odoo Core (tương tự trường `standard_price` của `product.product`).
- **Hệ quả và Trade-off**:
  - Ưu điểm: Tuân thủ 100% chuẩn Odoo Core; trong PostgreSQL dữ liệu được lưu dưới dạng cột `jsonb` có độ chính xác số học cao; giao diện người dùng hiển thị trực quan đúng bản chất tiền tệ.
  - Điểm cần lưu ý: Giá trị ở tầng Python model là `float`, kiểm soát độ chính xác phần thập phân thông qua cấu hình `digits="Product Price"` kết hợp cơ chế làm tròn `float_round` của framework.

